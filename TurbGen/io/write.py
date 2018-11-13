"""
This module is for writing data to various formats.

The functions in this module were translated directly from the
original TSsubs.f90 file.
"""
from .base import convname
import numpy as np
from struct import pack
from .base import e
from .. import _version as ver
import time
from .sum import write as sum  # Make sum.write available here.
import h5py


def bladed(fname, tgdata):
    """Write tgdata to a Bladed-format (.wnd) binary file.

    Parameters
    ----------
    fname : str
            The filename to which the data should be written.
    tgdata : :class:`tgdata <TurbGen.main.tgdata>`
            A TurbGen data object.

    Notes
    -----

    Bladed is a Trademark of GL Garrad-Hassan.
    """
    prms = tgdata.parameters
    lat = prms.get('Latitude', 0.0)
    Z0 = prms.get('Z0', 0.0)
    ts = tgdata.utotal
    ti = np.sqrt(tgdata.tke[:, tgdata.ihub[0], tgdata.ihub[1]]) / tgdata.UHUB
    ti[ti < 1e-5] = 1
    scale = 1000. / (tgdata.UHUB * ti[:, None, None, None])
    off = np.array([1000. / (ti[0]), 0, 0])[:, None, None, None]
    fl = file(convname(fname, '.wnd'), 'wb')
    # First write some setup data:
    fl.write(pack(e + '2hl3f',
                  -99,
                  4,
                  3,
                  lat,
                  Z0,
                  tgdata.grid.z[0] + tgdata.grid.height / 2.0))
    # Now write the turbulence intensity, grid spacing, numsteps, and hub mean wind speed
    # For some reason this takes half the number of timesteps...
    fl.write(pack(e + '3f', * (100 * ti)))
    fl.write(pack(e + '3flf',
                  tgdata.grid.dz,
                  tgdata.grid.dy,
                  tgdata.UHUB * tgdata.dt,
                  tgdata.shape[-1] / 2,
                  tgdata.UHUB))
    fl.write(pack(e + '3f', *([0] * 3)))  # Unused bytes
    # Previously this was unused. Now I am using it to store the clockwise flag.
    # 0 is reserved for TurbSim (no specification), 1 is False, 2 is True.
    fl.write(pack(e + 'l', (tgdata.grid.clockwise + 1)))
    fl.write(pack(e + '3l',
                  tgdata.info['RandSeed'],
                  tgdata.grid.n_z,
                  tgdata.grid.n_y))
    fl.write(pack(e + '6l', *([0] * 6)))  # Unused bytes
    if tgdata.grid.clockwise:
        out = (ts[:, :, ::-1, :] * scale - off).astype(np.int16)
    else:
        out = (ts[:, :, :, :] * scale - off).astype(np.int16)
    # Swap the y and z indices so that fortran-order writing agrees with the
    # file format.
    out = np.rollaxis(out, 2, 1)
    # Write the data so that the first index varies fastest (F order).
    # With the swap of y and z indices above, the indexes vary in the following
    # (decreasing) order:
    # component (fastest), y-index, z-index, time (slowest).
    fl.write(out.tostring(order='F'))
    fl.close()


def formatted(fname, tgdata, verbose=False):
    """Write the data to a set of TurbSim 'formatted' (readable) files (.u, .v, .w).

    Parameters
    ----------
    fname : str
            the base-filename to which the data should be written.
            '.u', '.v', '.w' will be appended to fname for each file.
    tgdata : :class:`tgdata <TurbGen.main.tgdata>`
             The 'tgdata' object that contains the data.

    """

    header = ("\nThis full-field turbulence file was generated by {ver.__prog_name__} "
              "(v{ver.__version__}, {ver.__version_date__}) on {date} at {time}.".format(
                  ver=ver,
                  date=time.strftime('%d-%b-%Y', time.localtime()),
                  time=time.strftime('%H:%M:%S (%Z)', time.localtime())))
    header += ("\n\n"
               " | %s-comp |  Y  x  Z  | Grid Resolution (Y x Z) | "
               "Time-step | Hub Elev | Mean U |\n"
               "          {n_y: 4d}  {n_z: 4d}  {dy: 9.3f}  {dz: 9.3f}   "
               "   {dt:9.3f}  {zhub:9.2f} {uhub:9.2f}\n"
               "\n"
               " Z Coordinates (m):\n"
               " {zcoords}\n"
               "\n"
               " Y Coordinates (m):\n"
               " {ycoords}\n".format(n_y=tgdata.grid.n_y,
                                     n_z=tgdata.grid.n_z,
                                     dy=tgdata.grid.dy,
                                     dz=tgdata.grid.dz,
                                     dt=tgdata.dt,
                                     zhub=tgdata.grid.zhub,
                                     uhub=tgdata.UHUB,
                                     zcoords=(' {: 7.3f}' * tgdata.grid.n_z).format(*tgdata.z),
                                     ycoords=(' {: 7.3f}' * tgdata.grid.n_y).format(*tgdata.y), ))
    outform = ("\n"
               "  {: 7.3f} {: 7.3f}\n")
    outform += (' ' + (' {: 7.3f}' * tgdata.grid.n_y) + '\n') * tgdata.grid.n_z

    fname = fname.rstrip('.inp')

    if verbose:
        print("Writing formatted files...")
    for idc in range(tgdata.n_comp):
        comp = tgdata.comp_name[idc]
        if verbose:
            print("{}-component, timestep:".format(comp))
        fl = open(fname + '.' + comp, 'w')
        fl.write(header % (comp))
        nt = tgdata.time.shape[0]
        for idt in range(nt):
            if verbose and idt % 1000 == 0:
                print('{}/{}'.format(idt, nt))
            fl.write(outform.format(tgdata.time[idt],
                                    tgdata.uhub[idt],
                                    *tgdata.uturb[idc, :, :, idt].flatten()))
        fl.close()


def turbsim(fname, tgdata):
    """Write the data to a TurbSim-format binary file (.bts).

    Parameters
    ----------
    fname : str
            the filename to which the data should be written.
    tgdata : :class:`tgdata <TurbGen.main.tgdata>`
             The 'tgdata' object that contains the data.

    """
    ts = tgdata.utotal
    intmin = -32768
    intrng = 65536
    u_minmax = np.empty((3, 2), dtype=np.float32)
    u_off = np.empty((3), dtype=np.float32)
    u_scl = np.empty((3), dtype=np.float32)
    desc_str = 'generated by %s v%s, %s.' % (
        ver.__prog_name__,
        ver.__version__,
        time.strftime('%b %d, %Y, %H:%M (%Z)', time.localtime()))
    # Calculate the ranges:
    out = np.empty(tgdata.shape, dtype=np.int16)
    for ind in range(3):
        u_minmax[ind] = ts[ind].min(), ts[ind].max()
        if u_minmax[ind][0] == u_minmax[ind][1]:
            u_scl[ind] = 1
        else:
            u_scl[ind] = intrng / np.diff(u_minmax[ind])
        u_off[ind] = intmin - u_scl[ind] * u_minmax[ind, 0]
        out[ind] = (ts[ind] * u_scl[ind] + u_off[ind]).astype(np.int16)
    fl = file(convname(fname, '.bts'), 'wb')
    fl.write(pack(e + 'h4l12fl',
                  7,
                  tgdata.grid.n_z,
                  tgdata.grid.n_y,
                  tgdata.grid.n_tower,
                  tgdata.shape[-1],
                  tgdata.grid.dz,
                  tgdata.grid.dy,
                  tgdata.dt,
                  tgdata.UHUB,
                  tgdata.grid.zhub,
                  tgdata.grid.z[0],
                  u_scl[0],
                  u_off[0],
                  u_scl[1],
                  u_off[1],
                  u_scl[2],
                  u_off[2],
                  len(desc_str)))
    fl.write(desc_str)
    # Swap the y and z indices so that fortran-order writing agrees with the file format.
    # Also, we swap the order of z-axis to agree with the file format.
    # Write the data so that the first index varies fastest (F order).
    # The indexes vary in the following order:
    # component (fastest), y-index, z-index, time (slowest).
    fl.write(np.rollaxis(out, 2, 1).tostring(order='F'))
    fl.close()


def hdf5(fname, tgdata):
    """Write the data to an hdf5 file.

    Parameters
    ----------
    fname : str
            the filename to which the data should be written. `.inp`
            will always be stripped, and `.h5` will be added if no
            file extension exists.
    tgdata : :class:`tgdata <TurbGen.main.tgdata>`
             The 'tgdata' object that contains the data.

    """
    fname = fname.rstrip('.inp')
    if '.' not in (fname.split('/')[-1]).split('\\')[-1]:
        fname += '.h5'
    with h5py.File(fname, mode='w') as fl:
        # The turbulence velocity:
        ds_uturb = fl.create_dataset('uturb', data=tgdata.uturb)
        ds_uturb.attrs.create('units', 'm/s')
        ds_uturb.attrs.create('dims', ['u,v,w', 'z', 'y', 'time'])
        # The mean velocity profile:
        ds_uprof = fl.create_dataset('uprof', data=tgdata.uprof)
        ds_uprof.attrs.create('units', 'm/s')
        ds_uprof.attrs.create('dims', ['u,v,w', 'z', 'y'])
        # The spatial grid:
        ds_z = fl.create_dataset('z', data=tgdata.z)
        ds_z.attrs.create('units', 'm')
        ds_y = fl.create_dataset('y', data=tgdata.y)
        ds_y.attrs.create('units', 'm')
        # The time vector:
        ds_time = fl.create_dataset('time', data=tgdata.time)
        ds_time.attrs.create('units', 'sec')
