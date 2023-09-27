import pathlib as pl

import flopy
import numpy as np
import pytest
from flopy.utils.gridgen import Gridgen

from framework import TestFramework
from simulation import TestSimulation

dis_types = (
    "disv",
    "disu",
)
problems = (
    "ps1a",
    "ps2a",
    "ps2a_list",
    "ps2b",
)
ex = []
for problem in problems:
    ex += [f"{problem}_{dis_type}" for dis_type in dis_types]
# remove invalid combinations
for tag in ("ps2a_disu", "ps2b_disu"):
    ex.remove(tag)

paktest = "csub"

# base spatial discretization
nlay, nrow, ncol = 3, 21, 20
shape3d = (nlay, nrow, ncol)
shape2d = (nrow, ncol)
size3d = nlay * nrow * ncol
size2d = nrow * ncol

delr = delc = 500.0
x0_base, x1_base, y0_base, y1_base = 0, ncol * delr, 0.0, nrow * delc
top = 400.0
bot = 0.0
botm = [220.0, 200.0, 0.0]
z_node = [310.0, 210.0, 100.0]

hk = [50.0, 0.01, 200.0]
vk = [10.0, 0.01, 20.0]

canal_head = 330.0
canal_coordinates = [
    (0.5 * delr, y1_base - delr * (i + 0.5)) for i in range(nrow)
]

river_head = 320.0
river_coordinates = [
    (x1_base - 0.5 * delr, y1_base - delr * (i + 0.5)) for i in range(nrow)
]

rch_rate = 0.005


def build_dis(gwf):
    return flopy.mf6.ModflowGwfdis(
        gwf,
        nlay=nlay,
        nrow=nrow,
        ncol=ncol,
        delr=delr,
        delc=delc,
        top=top,
        botm=botm,
    )


def get_gridgen_ws(ws):
    gridgen_ws = ws / "gridgen"
    gridgen_ws.mkdir(parents=True, exist_ok=True)
    return gridgen_ws


def get_dis_name(name):
    return name.replace("disv", "dis").replace("disu", "dis")


def build_temp_gwf(ws):
    gridgen_ws = get_gridgen_ws(ws)
    gridgen_sim = flopy.mf6.MFSimulation(
        sim_name="gridgen", sim_ws=gridgen_ws, exe_name="mf6"
    )
    gridgen_gwf = flopy.mf6.ModflowGwf(gridgen_sim, modelname="gridgen")
    return gridgen_gwf


def build_disv(ws, gwf, gridgen):
    temp_gwf = build_temp_gwf(ws)
    dis = build_dis(temp_gwf)
    g = Gridgen(
        temp_gwf.modelgrid,
        model_ws=get_gridgen_ws(ws),
        exe_name=gridgen,
    )
    g.build()
    gridprops = g.get_gridprops_disv()
    return flopy.mf6.ModflowGwfdisv(gwf, **gridprops)


def build_disu(ws, gwf, gridgen):
    temp_gwf = build_temp_gwf(ws)
    dis = build_dis(temp_gwf)
    g = Gridgen(
        temp_gwf.modelgrid,
        model_ws=get_gridgen_ws(ws),
        exe_name=gridgen,
    )
    g.build()
    gridprops = g.get_gridprops_disu6()
    return flopy.mf6.ModflowGwfdisu(gwf, **gridprops)


def get_node_number(modelgrid, cellid):
    if modelgrid.grid_type == "unstructured":
        node = cellid
    elif modelgrid.grid_type == "vertex":
        node = modelgrid.ncpl * cellid[0] + cellid[1]
    else:
        node = (
            modelgrid.nrow * modelgrid.ncol * cellid[0]
            + modelgrid.ncol * cellid[1]
            + cellid[2]
        )
    return node


def build_3d_array(modelgrid, values, dtype=float):
    if isinstance(values, dtype):
        arr = np.full(modelgrid.nnodes, values, dtype=dtype)
    else:
        arr = np.zeros(modelgrid.nnodes, dtype=dtype)
        ia = []
        x0, x1, y0, y1 = modelgrid.extent
        for k in range(nlay):
            cellid = modelgrid.intersect(x0 + 0.1, y1 - 0.1, z=z_node[k])
            ia.append(get_node_number(modelgrid, cellid))
        ia.append(modelgrid.nnodes + 1)
        for k in range(nlay):
            arr[ia[k] : ia[k + 1]] = values[k]
    return arr.reshape(modelgrid.shape)


def build_chd_data(modelgrid, coordinates, head, layer_number=0):
    chd_spd = []
    for x, y in coordinates:
        cellid = modelgrid.intersect(x, y, z=z_node[layer_number])
        if isinstance(cellid, tuple):
            chd_spd.append((*cellid, head))
        else:
            chd_spd.append((cellid, head))
    return {0: chd_spd}


def build_riv_data(modelgrid):
    cond = 20.0 * 10 * delc / 1.0
    spd = []
    for x, y in river_coordinates:
        cellid = modelgrid.intersect(x, y, z=z_node[0])
        if isinstance(cellid, int):
            cellid = (cellid,)
        spd.append((*cellid, river_head, cond, 317.0))
    return {0: spd}


def build_rch_package(gwf, name):
    if "list" in name or name.endswith("disu"):
        spd = []
        for i in range(nrow):
            y = y1_base - delr * (i + 0.5)
            for j in range(ncol):
                x = delc * (j + 0.5)
                cellid = gwf.modelgrid.intersect(x, y, z=z_node[0])
                if isinstance(cellid, int):
                    cellid = (cellid,)
                spd.append((*cellid, rch_rate))
        rch = flopy.mf6.ModflowGwfrch(gwf, stress_period_data=spd)
    else:
        rch = flopy.mf6.ModflowGwfrcha(gwf, recharge=rch_rate)
    return rch


def build_model(idx, ws, gridgen):
    return build_mf6(idx, ws, gridgen), build_mf6(idx, ws / "mf6", gridgen)


# build MODFLOW 6 files
def build_mf6(idx, ws, gridgen):
    if ws.name == "mf6":
        dis_type = "dis"
    elif "disv" in str(ws):
        dis_type = "disv"
    elif "disu" in str(ws):
        dis_type = "disu"
    else:
        raise ValueError(f"Invalid discretization type in {str(ws)}")

    name = ex[idx]
    if dis_type == "dis":
        name = get_dis_name(name)
    sim = flopy.mf6.MFSimulation(
        sim_name=name,
        version="mf6",
        exe_name="mf6",
        sim_ws=ws,
    )
    # create tdis package
    tdis = flopy.mf6.ModflowTdis(
        sim,
        time_units="DAYS",
    )

    # create iterative model solution and register the gwf model with it
    ims = flopy.mf6.ModflowIms(
        sim,
        print_option="SUMMARY",
        complexity="simple",
    )

    # create gwf model
    gwf = flopy.mf6.ModflowGwf(
        sim,
        modelname=name,
        print_input=True,
        save_flows=True,
    )

    if dis_type == "disv":
        dis = build_disv(ws, gwf, gridgen)
    elif dis_type == "disu":
        dis = build_disu(ws, gwf, gridgen)
    else:
        dis = build_dis(gwf)

    # initial conditions
    ic = flopy.mf6.ModflowGwfic(
        gwf,
        strt=top,
    )

    if dis_type in ("dis", "disv"):
        k11 = hk
        k33 = vk
        icelltype = [1, 0, 0]
    else:
        k11 = build_3d_array(gwf.modelgrid, hk)
        k33 = build_3d_array(gwf.modelgrid, vk)
        icelltype = build_3d_array(gwf.modelgrid, [1, 0, 0], dtype=int)

    # node property flow
    npf = flopy.mf6.ModflowGwfnpf(
        gwf,
        icelltype=icelltype,
        k=k11,
        k33=k33,
    )

    # canal chd
    if name.startswith("ps1"):
        canal_chd = flopy.mf6.ModflowGwfchd(
            gwf,
            filename=f"{name}.canal.chd",
            pname="canal",
            stress_period_data=build_chd_data(
                gwf.modelgrid,
                canal_coordinates,
                canal_head,
            ),
        )

    if name.startswith("ps1") or name.startswith("ps2a"):
        river_chd = flopy.mf6.ModflowGwfchd(
            gwf,
            filename=f"{name}.river.chd",
            pname="river",
            stress_period_data=build_chd_data(
                gwf.modelgrid,
                river_coordinates,
                river_head,
            ),
        )
    elif name.startswith("ps2b"):
        river_riv = flopy.mf6.ModflowGwfriv(
            gwf,
            pname="river",
            stress_period_data=build_riv_data(
                gwf.modelgrid,
            ),
        )

    if name.startswith("ps2"):
        rch = build_rch_package(gwf, name)

    # output control
    oc = flopy.mf6.ModflowGwfoc(
        gwf,
        budget_filerecord=f"{name}.cbc",
        head_filerecord=f"{name}.hds",
        headprintrecord=[("COLUMNS", 10, "WIDTH", 15, "DIGITS", 6, "GENERAL")],
        saverecord=[("HEAD", "ALL"), ("BUDGET", "ALL")],
        printrecord=[("HEAD", "ALL"), ("BUDGET", "ALL")],
    )
    return sim


def eval_head(sim):
    name = ex[sim.idxsim]
    ws = pl.Path(sim.simpath)

    print(f"evaluating {name} heads...")

    if name.startswith("ps1"):
        row_values = np.array(
            [
                330.000,
                329.259,
                328.600,
                328.008,
                327.473,
                326.983,
                326.529,
                326.102,
                325.694,
                325.297,
                324.903,
                324.504,
                324.092,
                323.659,
                323.195,
                322.691,
                322.133,
                321.510,
                320.805,
                320.000,
            ]
        )
    elif name.startswith("ps2a"):
        row_values = np.array(
            [
                346.054,
                345.979,
                345.828,
                345.598,
                345.286,
                344.886,
                344.391,
                343.792,
                343.079,
                342.238,
                341.251,
                340.099,
                338.755,
                337.189,
                335.362,
                333.224,
                330.714,
                327.750,
                324.227,
                320.000,
            ]
        )
    elif name.startswith("ps2b"):
        row_values = np.array(
            [
                346.268,
                346.193,
                346.042,
                345.813,
                345.500,
                345.100,
                344.606,
                344.008,
                343.295,
                342.454,
                341.468,
                340.316,
                338.974,
                337.410,
                335.584,
                333.449,
                330.943,
                327.984,
                324.468,
                320.250,
            ]
        )
    else:
        row_values = None
    if row_values is None:
        answer = None
    else:
        answer = np.zeros(shape2d)
        for i in range(nrow):
            answer[i, :] = row_values[:]

    # get disv or disu simulation
    sim_base = flopy.mf6.MFSimulation.load(sim_name=name, sim_ws=ws)
    gwf_base = sim_base.get_model()

    head = gwf_base.output.head().get_data().flatten().reshape(shape3d)
    if answer is not None:
        assert np.allclose(
            head[0], answer
        ), "head data for first layer does not match know result"

    extension = "cbc"
    fpth0 = ws / f"{name}.{extension}"
    fpth1 = ws / f"mf6/{get_dis_name(name)}.{extension}"
    sim.compare_budget_files(0, extension, fpth0, fpth1)

    return


@pytest.mark.parametrize(
    "idx, name",
    list(enumerate(ex)),
)
def test_mf6model(idx, name, function_tmpdir, targets):
    ws = function_tmpdir
    test = TestFramework()
    test.build(lambda i, w: build_model(i, w, targets.gridgen), idx, ws)
    test.run(
        TestSimulation(
            name=name,
            exe_dict=targets,
            exfunc=eval_head,
            cmp_verbose=False,
            idxsim=idx,
            make_comparison=True,
        ),
        ws,
    )
