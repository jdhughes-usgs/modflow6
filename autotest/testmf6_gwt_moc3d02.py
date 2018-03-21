import os
import sys
import numpy as np

try:
    import pymake
except:
    msg = 'Error. Pymake package is not available.\n'
    msg += 'Try installing using the following command:\n'
    msg += ' pip install https://github.com/modflowpy/pymake/zipball/master'
    raise Exception(msg)

try:
    import flopy
except:
    msg = 'Error. FloPy package is not available.\n'
    msg += 'Try installing using the following command:\n'
    msg += ' pip install flopy'
    raise Exception(msg)

from framework import testing_framework
from simulation import Simulation

ex = ['moc3d02']
exdirs = []
for s in ex:
    exdirs.append(os.path.join('temp', s))
ddir = 'data'


def build_models():
    nlay, nrow, ncol = 40, 12, 30
    nper = 1
    perlen = [400]
    nstp = [400]
    tsmult = [1.]
    steady = [True]
    delr = 3.0
    delc = 0.5
    top = 0.
    delz = 0.05
    botm =  np.arange(-delz, -nlay*delz - delz, -delz)
    strt = 0.
    hnoflo = 1e30
    hdry = -1e30
    hk = 0.0125 / delz
    laytyp = 0
    diffc = 0.
    alphal = 0.6
    alphath = 0.03
    alphatv = 0.006
    porosity = 0.25
    #ss = 0.
    #sy = 0.1

    nouter, ninner = 100, 300
    hclose, rclose, relax = 1e-8, 1e-6, 1.

    tdis_rc = []
    for idx in range(nper):
        tdis_rc.append((perlen[idx], nstp[idx], tsmult[idx]))

    for idx, dir in enumerate(exdirs):
        name = ex[idx]

        # build MODFLOW 6 files
        ws = dir
        sim = flopy.mf6.MFSimulation(sim_name=name, version='mf6',
                                     exe_name='mf6',
                                     sim_ws=ws)
        # create tdis package
        tdis = flopy.mf6.ModflowTdis(sim, time_units='DAYS',
                                     nper=nper, perioddata=tdis_rc)

        # create gwf model
        gwfname = 'gwf_' + name
        gwf = flopy.mf6.MFModel(sim, model_type='gwf6', modelname=gwfname,
                                model_nam_file='{}.nam'.format(gwfname))

        # create iterative model solution and register the gwf model with it
        imsgwf = flopy.mf6.ModflowIms(sim, print_option='SUMMARY',
                                      outer_hclose=hclose,
                                      outer_maximum=nouter,
                                      under_relaxation='NONE',
                                      inner_maximum=ninner,
                                      inner_hclose=hclose, rcloserecord=rclose,
                                      linear_acceleration='CG',
                                      scaling_method='NONE',
                                      reordering_method='NONE',
                                      relaxation_factor=relax,
                                      fname='{}.ims'.format(gwfname))
        sim.register_ims_package(imsgwf, [gwf.name])

        dis = flopy.mf6.ModflowGwfdis(gwf, nlay=nlay, nrow=nrow, ncol=ncol,
                                      delr=delr, delc=delc,
                                      top=top, botm=botm,
                                      idomain=np.ones((nlay, nrow, ncol), dtype=np.int),
                                      fname='{}.dis'.format(gwfname))

        # initial conditions
        ic = flopy.mf6.ModflowGwfic(gwf, strt=strt,
                                    fname='{}.ic'.format(gwfname))

        # node property flow
        npf = flopy.mf6.ModflowGwfnpf(gwf, save_flows=False,
                                      save_specific_discharge=True,
                                      icelltype=laytyp,
                                      k=hk,
                                      k33=hk)
        # storage
        #sto = flopy.mf6.ModflowGwfsto(gwf, save_flows=False,
        #                              iconvert=laytyp[idx],
        #                              ss=ss[idx], sy=sy[idx],
        #                              steady_state={0: True, 2: True},
        #                              transient={1: True})

        # chd files
        chdlist = []
        j = ncol - 1
        for k in range(nlay):
            for i in range(nrow):
                chdlist.append([(k, i, j), 0.])
        chd = flopy.mf6.ModflowGwfchd(gwf,
                                      stress_period_data=chdlist,
                                      save_flows=False,
                                      pname='CHD-1')

        # wel files
        wellist = []
        j = 0
        qwell = 0.1 * delz * delc * porosity
        for k in range(nlay):
            for i in range(nrow):
                wellist.append([(k, i, j), qwell, 0.])
        wellist.append([(0, 0, 7), 1.e-6, 2.5e6])  # source well

        wel = flopy.mf6.ModflowGwfwel(gwf,
                                      print_input=True,
                                      print_flows=True,
                                      stress_period_data=wellist,
                                      save_flows=False,
                                      auxiliary='CONCENTRATION',
                                      pname='WEL-1')

        # output control
        oc = flopy.mf6.ModflowGwfoc(gwf,
                                    budget_filerecord='{}.cbc'.format(gwfname),
                                    head_filerecord='{}.hds'.format(gwfname),
                                    headprintrecord=[
                                        ('COLUMNS', 10, 'WIDTH', 15,
                                         'DIGITS', 6, 'GENERAL')],
                                    saverecord=[('HEAD', 'LAST')],
                                    printrecord=[('HEAD', 'LAST'),
                                                 ('BUDGET', 'LAST')])

        # create gwt model
        gwtname = 'gwt_' + name
        gwt = flopy.mf6.MFModel(sim, model_type='gwt6', modelname=gwtname,
                                model_nam_file='{}.nam'.format(gwtname))

        # create iterative model solution and register the gwt model with it
        imsgwt = flopy.mf6.ModflowIms(sim, print_option='SUMMARY',
                                      outer_hclose=hclose,
                                      outer_maximum=nouter,
                                      under_relaxation='NONE',
                                      inner_maximum=ninner,
                                      inner_hclose=hclose, rcloserecord=rclose,
                                      linear_acceleration='BICGSTAB',
                                      scaling_method='NONE',
                                      reordering_method='NONE',
                                      relaxation_factor=relax,
                                      fname='{}.ims'.format(gwtname))
        sim.register_ims_package(imsgwt, [gwt.name])

        dis = flopy.mf6.ModflowGwtdis(gwt, nlay=nlay, nrow=nrow, ncol=ncol,
                                      delr=delr, delc=delc,
                                      top=top, botm=botm,
                                      idomain=1,
                                      fname='{}.dis'.format(gwtname))

        # initial conditions
        strt = np.zeros((nlay, nrow, ncol))
        strt[0, 0, 0] = 0.
        ic = flopy.mf6.ModflowGwtic(gwt, strt=strt,
                                    fname='{}.ic'.format(gwtname))

        # advection
        adv = flopy.mf6.ModflowGwtadv(gwt, scheme='TVD',
                                      fname='{}.adv'.format(gwtname))

        # dispersion
        dsp = flopy.mf6.ModflowGwtdsp(gwt, xt3d=True, diffc=diffc,
                                      alh=alphal, alv=alphal,
                                      ath=alphath, atv=alphatv,
                                      fname='{}.dsp'.format(gwtname))

        # storage
        sto = flopy.mf6.ModflowGwtsto(gwt, porosity=porosity,
                                    fname='{}.sto'.format(gwtname))

        # sources
        sourcerecarray = [('WEL-1', 1, 'CONCENTRATION')]
        ssm = flopy.mf6.ModflowGwtssm(gwt, sources=sourcerecarray,
                                    fname='{}.ssm'.format(gwtname))

        # output control
        oc = flopy.mf6.ModflowGwtoc(gwt,
                                    budget_filerecord='{}.cbc'.format(gwtname),
                                    concentration_filerecord='{}.ucn'.format(gwtname),
                                    concentrationprintrecord=[
                                        ('COLUMNS', 10, 'WIDTH', 15,
                                         'DIGITS', 6, 'GENERAL')],
                                    saverecord=[('CONCENTRATION', 'ALL')],
                                    printrecord=[('CONCENTRATION', 'LAST'),
                                                 ('BUDGET', 'LAST')])

        # GWF GWT exchange
        gwfgwt = flopy.mf6.ModflowGwfgwt(sim, exgtype='GWF6-GWT6',
                                         exgmnamea=gwfname, exgmnameb=gwtname,
                                         fname='{}.gwfgwt'.format(name))

        # write MODFLOW 6 files
        sim.write_simulation()

    return


def eval_transport(sim):
    print('evaluating transport...')

    name = ex[sim.idxsim]
    gwtname = 'gwt_' + name

    fpth = os.path.join(sim.simpath, '{}.ucn'.format(gwtname))
    try:
        cobj = flopy.utils.HeadFile(fpth, precision='double',
                                    text='CONCENTRATION')
    except:
        assert False, 'could not load data from "{}"'.format(fpth)


    return


# - No need to change any code below
def test_mf6model():
    # initialize testing framework
    test = testing_framework()

    # build the models
    build_models()

    # run the test models
    for idx, dir in enumerate(exdirs):
        yield test.run_mf6, Simulation(dir, exfunc=eval_transport, idxsim=idx)

    return


def main():
    # initialize testing framework
    test = testing_framework()

    # build the models
    build_models()

    # run the test models
    for idx, dir in enumerate(exdirs):
        sim = Simulation(dir, exfunc=eval_transport, idxsim=idx)
        test.run_mf6(sim)

    return


if __name__ == "__main__":
    # print message
    print('standalone run of {}'.format(os.path.basename(__file__)))

    # run main routine
    main()
