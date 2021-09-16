"""
Contains GRB class, with method to load and truncate data for SGRB and in future LGRB
"""
import matplotlib.pyplot as plt
import numpy as np
import os
import pandas as pd
from redback.redback.utils import logger

from astropy.cosmology import Planck18 as cosmo
from ..getdata import afterglow_directory_structure
from os.path import join

from .. import models as mm
from ..model_library import all_models_dict
from ..utils import find_path
from .transient import Transient

dirname = os.path.dirname(__file__)

DATA_MODES = ['luminosity', 'flux', 'flux_density', 'photometry']


class Afterglow(Transient):
    """Class for afterglows"""
    def __init__(self, name, data_mode='flux'):
        """
        :param name: Telephone number of SGRB, e.g., GRB 140903A
        """
        if not name.startswith('GRB'):
            name = 'GRB' + name
        super().__init__(time=[], time_err=[], y=[], y_err=[], data_mode=data_mode, name=name)

        self.time = np.array([])
        self.time_rest_frame = np.array([])
        self.time_err = np.array([])
        self.time_rest_frame_err = np.array([])
        self.Lum50 = np.array([])
        self.Lum50_err = np.array([])
        self.flux_density = np.array([])
        self.flux_density_err = np.array([])
        self.flux = np.array([])
        self.flux_err = np.array([])

        self.data_mode = data_mode

        self._set_data()
        self._set_photon_index()
        self._set_t90()
        self._get_redshift()

        self.load_data(data_mode=self.data_mode)


    # def get_luminosity_attributes(self):
    #     #do sql stuff.
    #     pass
    #
    # def numerical_luminosity_from_flux(self):
    #     pass

    @property
    def _stripped_name(self):
        return self.name.lstrip('GRB')

    @property
    def luminosity_data(self):
        return self.data_mode == DATA_MODES[0]

    @property
    def flux_data(self):
        return self.data_mode == DATA_MODES[1]

    @property
    def fluxdensity_data(self):
        return self.data_mode == DATA_MODES[2]

    @property
    def photometry_data(self):
        return self.data_mode == DATA_MODES[3]

    @classmethod
    def from_path_and_grb(cls, path, grb):
        data_dir = find_path(path)
        return cls(name=grb, path=data_dir)

    @classmethod
    def from_path_and_grb_with_truncation(
            cls, path, grb, truncate=True, truncate_method='prompt_time_error', data_mode='flux'):
        grb = cls.from_path_and_grb(path=path, grb=grb)
        grb.load_and_truncate_data(truncate=truncate, truncate_method=truncate_method, data_mode=data_mode)
        return grb

    def load_and_truncate_data(self, truncate=True, truncate_method='prompt_time_error', data_mode='flux'):
        """
        Read data of SGRB from given path and GRB telephone number.
        Truncate the data to get rid of all but the last prompt emission point
        make a cut based on the size of the temporal error; ie if t_error < 1s, the data point is
        part of the prompt emission
        """
        self.load_data(data_mode=data_mode)
        if truncate:
            self.truncate(truncate_method=truncate_method)

    def load_data(self, data_mode=None):
        if data_mode is not None:
            self.data_mode = data_mode

        grb_dir, _, _ = afterglow_directory_structure(grb=self._stripped_name, use_default_directory=False,
                                                      data_mode=self.data_mode)
        filename = f"{self.name}.csv"

        data_file = join(grb_dir, filename)
        data = np.genfromtxt(data_file, delimiter=",")[1:]
        if self.luminosity_data:
            self.time_rest_frame = data[:, 0]  # time (secs)
            self.time_rest_frame_err = np.abs(data[:, 1:3].T)  # \Delta time (secs)
            self.Lum50, self.Lum50_err = self._load(data)  # Lum (1e50 erg/s)
        elif self.fluxdensity_data:
            self.time = data[:, 0]  # time (secs)
            self.time_err = np.abs(data[:, 1:3].T)  # \Delta time (secs)
            self.flux_density, self.flux_density_err = self._load(data)  # depending on detector its at a specific mJy
        elif self.flux_data:
            self.time = data[:, 0]  # time (secs)
            self.time_err = np.abs(data[:, 1:3].T)  # \Delta time (secs)
            self.flux, self.flux_err = self._load(data)  # depending on detector its over a specific frequency range

    @staticmethod
    def _load(data):
        return np.array(data[:, 3]), np.array(np.abs(data[:, 4:].T))

    def truncate(self, truncate_method='prompt_time_error'):
        if truncate_method == 'prompt_time_error':
            self._truncate_prompt_time_error()
        elif truncate_method == 'left_of_max':
            self._truncate_left_of_max()
        else:
            self._truncate_default()

    def _truncate_prompt_time_error(self):
        if self.luminosity_data:
            mask1 = self.time_rest_frame_err[0, :] > 0.0025
            mask2 = self.time_rest_frame < 2.0  # dont truncate if data point is after 2.0 seconds
        else:
            mask1 = self.time_err[0, :] > 0.0025
            mask2 = self.time < 2.0  # dont truncate if data point is after 2.0 seconds

        mask = np.logical_and(mask1, mask2)
        if self.luminosity_data:
            self.time_rest_frame = self.time_rest_frame[~mask]
            self.time_rest_frame_err = self.time_rest_frame_err[:, ~mask]
            self.Lum50 = self.Lum50[~mask]
            self.Lum50_err = self.Lum50_err[:, ~mask]
        elif self.flux_data:
            self.flux = self.flux[~mask]
            self.flux_err = self.flux_err[:, ~mask]
        elif self.fluxdensity_data:
            self.flux_density = self.flux_density[~mask]
            self.flux_density_err = self.flux_density_err[:, ~mask]

    def _truncate_left_of_max(self):
        if self.luminosity_data:
            max_index = np.argmax(self.Lum50)
            self.time_rest_frame = self.time_rest_frame[max_index:]
            self.time_rest_frame_err = self.time_rest_frame_err[:, max_index:]
            self.Lum50 = self.Lum50[max_index:]
            self.Lum50_err = self.Lum50_err[:, max_index:]
        elif self.flux_data:
            max_index = np.argmax(self.flux)
            self.flux = self.flux[max_index:]
            self.flux_err = self.flux_err[:, max_index:]
        elif self.fluxdensity_data:
            max_index = np.argmax(self.flux_density)
            self.flux_density = self.flux_density[max_index:]
            self.flux_density_err = self.flux_density_err[:, max_index:]
        else:
            raise ValueError
        self.time = self.time[max_index:]
        self.time_err = self.time_err[:, max_index:]

    def _truncate_default(self):
        truncate = self.time_err[0, :] > 0.1
        to_del = len(self.time) - (len(self.time[truncate]) + 2)
        self.time = self.time[to_del:]
        self.time_err = self.time_err[:, to_del:]
        if self.luminosity_data:
            self.time_rest_frame = self.time_rest_frame[to_del:]
            self.time_rest_frame_err = self.time_rest_frame_err[:, to_del:]
            self.Lum50 = self.Lum50[to_del:]
            self.Lum50_err = self.Lum50_err[:, to_del:]
        elif self.flux_data:
            self.flux = self.flux[to_del:]
            self.flux_err = self.flux_err[:, to_del:]
        elif self.fluxdensity_data:
            self.flux_density = self.flux_density[to_del:]
            self.flux_density_err = self.flux_density_err[:, to_del:]

    @property
    def event_table(self):
        return os.path.join(dirname, f'../tables/{self.__class__.__name__}_table.txt')

    # def get_flux_density(self):
    #     pass
    #
    # def get_integrated_flux(self):
    #     pass

    def analytical_flux_to_luminosity(self):
        redshift = self._get_redshift_for_luminosity_calculation()
        if redshift is None:
            return

        luminosity_distance = cosmo.luminosity_distance(redshift).cgs.value
        k_corr = (1 + redshift) ** (self.photon_index - 2)
        isotropic_bolometric_flux = (luminosity_distance ** 2.) * 4. * np.pi * k_corr
        counts_to_flux_fraction = 1

        self._calculate_rest_frame_time_and_luminosity(
            counts_to_flux_fraction=counts_to_flux_fraction,
            isotropic_bolometric_flux=isotropic_bolometric_flux,
            redshift=redshift)
        self.data_mode = 'luminosity'
        self._save_luminosity_data()

    def numerical_flux_to_luminosity(self, counts_to_flux_absorbed, counts_to_flux_unabsorbed):
        try:
            from sherpa.astro import ui as sherpa
        except ImportError as e:
            logger.warning(e)
            logger.warning("Can't perform numerical flux to luminosity calculation")

        redshift = self._get_redshift_for_luminosity_calculation()
        if redshift is None:
            return

        Ecut = 1000
        obs_elow = 0.3
        obs_ehigh = 10

        bol_elow = 1.  # bolometric restframe low frequency in keV
        bol_ehigh = 10000.  # bolometric restframe high frequency in keV

        alpha = self.photon_index
        beta = self.photon_index

        sherpa.dataspace1d(obs_elow, bol_ehigh, 0.01)
        sherpa.set_source(sherpa.bpl1d.band)
        band.gamma1 = alpha  # noqa
        band.gamma2 = beta  # noqa
        band.eb = Ecut  # noqa

        luminosity_distance = cosmo.luminosity_distance(redshift).cgs.value
        k_corr = sherpa.calc_kcorr(redshift, obs_elow, obs_ehigh, bol_elow, bol_ehigh, id=1)
        isotropic_bolometric_flux = (luminosity_distance ** 2.) * 4. * np.pi * k_corr
        counts_to_flux_fraction = counts_to_flux_unabsorbed / counts_to_flux_absorbed

        self._calculate_rest_frame_time_and_luminosity(
            counts_to_flux_fraction=counts_to_flux_fraction,
            isotropic_bolometric_flux=isotropic_bolometric_flux,
            redshift=redshift)
        self.data_mode = 'luminosity'
        self._save_luminosity_data()

    def _get_redshift_for_luminosity_calculation(self):
        if np.isnan(self.redshift):
            logger.warning('This GRB has no measured redshift, using default z = 0.75')
            return 0.75
        elif self.data_mode == 'luminosity':
            logger.warning('The data is already in luminosity mode, returning.')
            return None
        elif self.data_mode == 'flux_density':
            logger.warning(f'The data needs to be in flux mode, but is in {self.data_mode}.')
            return None
        else:
            return self.redshift

    def _calculate_rest_frame_time_and_luminosity(self, counts_to_flux_fraction, isotropic_bolometric_flux, redshift):
        self.Lum50 = self.flux * counts_to_flux_fraction * isotropic_bolometric_flux * 1e-50
        self.Lum50_err = self.flux_err * isotropic_bolometric_flux * 1e-50
        self.time_rest_frame = self.time / (1 + redshift)
        self.time_rest_frame_err = self.time_err / (1 + redshift)

    def _save_luminosity_data(self):
        grb_dir, _, _ = afterglow_directory_structure(grb=self._stripped_name, use_default_directory=False,
                                                      data_mode=self.data_mode)
        filename = f"{self.name}.csv"
        data = {"Time in restframe [s]": self.time_rest_frame,
                "Pos. time err in restframe [s]": self.time_rest_frame_err[0, :],
                "Neg. time err in restframe [s]": self.time_rest_frame_err[1, :],
                "Luminosity [10^50 erg s^{-1}]": self.Lum50,
                "Pos. luminosity err [10^50 erg s^{-1}]": self.Lum50_err[0, :],
                "Neg. luminosity err [10^50 erg s^{-1}]": self.Lum50_err[1, :]}
        df = pd.DataFrame(data=data)
        df.to_csv(join(grb_dir, filename), index=False)

    # def get_prompt(self):
    #     pass
    #
    # def get_optical(self):
    #     pass

    def _set_data(self):
        data = pd.read_csv(self.event_table, header=0, error_bad_lines=False, delimiter='\t', dtype='str')
        data['BAT Photon Index (15-150 keV) (PL = simple power-law, CPL = cutoff power-law)'] = data[
            'BAT Photon Index (15-150 keV) (PL = simple power-law, CPL = cutoff power-law)'].fillna(0)
        self.data = data

    def _process_data(self):
        pass

    def _set_photon_index(self):
        photon_index = self.data.query('GRB == @self._stripped_name')[
            'BAT Photon Index (15-150 keV) (PL = simple power-law, CPL = cutoff power-law)'].values[0]
        if photon_index == 0.:
            return 0.
        self.photon_index = self.__clean_string(photon_index)

    def _get_redshift(self):
        # some GRBs dont have measurements
        redshift = self.data.query('GRB == @self._stripped_name')['Redshift'].values[0]
        if isinstance(self.redshift, str):
            self.redshift = self.__clean_string(redshift)
        elif np.isnan(redshift):
            return None
        else:
            self.redshift = redshift

    def _set_t90(self):
        # data['BAT Photon Index (15-150 keV) (PL = simple power-law, CPL = cutoff power-law)'] = data['BAT Photon
        # Index (15-150 keV) (PL = simple power-law, CPL = cutoff power-law)'].fillna(0)
        t90 = self.data.query('GRB == @self._stripped_name')['BAT T90 [sec]'].values[0]
        if t90 == 0.:
            return np.nan
        self.t90 = self.__clean_string(t90)

    @staticmethod
    def __clean_string(string):
        for r in ["PL", "CPL", ",", "C", "~", " ", 'Gemini:emission', '()']:
            string = string.replace(r, "")
        return float(string)

    # def process_grbs(self, use_default_directory=False):
    #     for GRB in self.data['GRB'].values:
    #         retrieve_and_process_data(GRB, use_default_directory=use_default_directory)
    #
    #     return print(f'Flux data for all {self.__class__.__name__}s added')
    #
    # @staticmethod
    # def process_grbs_w_redshift(use_default_directory=False):
    #     data = pd.read_csv(dirname + '/tables/GRBs_w_redshift.txt', header=0,
    #                        error_bad_lines=False, delimiter='\t', dtype='str')
    #     for GRB in data['GRB'].values:
    #         retrieve_and_process_data(GRB, use_default_directory=use_default_directory)
    #
    #     return print('Flux data for all GRBs with redshift added')
    #
    # @staticmethod
    # def process_grb_list(data, use_default_directory=False):
    #     """
    #     :param data: a list containing telephone number of GRB needing to process
    #     :param use_default_directory:
    #     :return: saves the flux file in the location specified
    #     """
    #
    #     for GRB in data:
    #         retrieve_and_process_data(GRB, use_default_directory=use_default_directory)
    #
    #     return print('Flux data for all GRBs in list added')

    def plot_data(self, axes=None, colour='k'):
        """
        plots the data
        GRB is the telephone number of the GRB
        :param axes:
        :param colour:
        """
        x, x_err, y, y_err, ylabel = self._get_plot_data_and_labels()

        ax = axes or plt.gca()
        ax.errorbar(x, y, xerr=x_err, yerr=y_err,
                    fmt='x', c=colour, ms=1, elinewidth=2, capsize=0.)

        ax.set_xscale('log')
        ax.set_yscale('log')

        ax.set_xlim(0.5 * x[0], 2 * (x[-1] + x_err[1][-1]))
        ax.set_ylim(0.5 * min(y), 2. * np.max(y))

        ax.annotate(f'GRB{self.name}', xy=(0.95, 0.9), xycoords='axes fraction',
                    horizontalalignment='right', size=20)

        ax.set_xlabel(r'Time since burst [s]')
        ax.set_ylabel(ylabel)
        ax.tick_params(axis='x', pad=10)

        if axes is None:
            plt.tight_layout()

        grb_dir, _, _ = afterglow_directory_structure(grb=self._stripped_name, use_default_directory=False,
                                                      data_mode=self.data_mode)
        filename = f"{self.name}_lc.png"
        plt.savefig(join(grb_dir, filename))
        plt.clf()

    def _get_plot_data_and_labels(self):
        if self.luminosity_data:
            x = self.time_rest_frame
            x_err = [self.time_rest_frame_err[1, :], self.time_rest_frame_err[0, :]]
            y = self.Lum50
            y_err = [self.Lum50_err[1, :], self.Lum50_err[0, :]]
            ylabel = r'Luminosity [$10^{50}$ erg s$^{-1}$]'
        elif self.flux_data:
            x = self.time
            x_err = [self.time_err[1, :], self.time_err[0, :]]
            y = self.flux
            y_err = [self.flux_err[1, :], self.flux_err[0, :]]
            ylabel = r'Flux [erg cm$^{-2}$ s$^{-1}$]'
        elif self.fluxdensity_data:
            x = self.time
            x_err = [self.time_err[1, :], self.time_err[0, :]]
            y = self.flux_density
            y_err = [self.flux_density_err[1, :], self.flux_density_err[0, :]]
            ylabel = r'Flux density [mJy]'
        else:
            raise ValueError
        return x, x_err, y, y_err, ylabel

    def plot_multiband(self):
        if self.data_mode != 'flux_density':
            logger.warning('why are you doing this')
        pass


class SGRB(Afterglow):
    pass


class LGRB(Afterglow):
    pass


# def plot_models(parameters, model, plot_magnetar, axes=None, colour='r', alpha=1.0, ls='-', lw=4):
#     """
#     plot the models
#     parameters: dictionary of parameters - 1 set of Parameters
#     model: model name
#     """
#     time = np.logspace(-4, 7, 100)
#     ax = axes or plt.gca()
#
#     lightcurve = all_models_dict[model]
#     magnetar_models = ['evolving_magnetar', 'evolving_magnetar_only', 'piecewise_radiative_losses',
#                        'radiative_losses', 'radiative_losses_mdr', 'radiative_losses_smoothness', 'radiative_only']
#     if model in magnetar_models and plot_magnetar:
#         if model == 'radiative_losses_mdr':
#             magnetar = mm.magnetar_only(time, nn=3., **parameters)
#         else:
#             magnetar = mm.magnetar_only(time, **parameters)
#         ax.plot(time, magnetar, color=colour, ls=ls, lw=lw, alpha=alpha, zorder=-32, linestyle='--')
#     ax.plot(time, lightcurve, color=colour, ls=ls, lw=lw, alpha=alpha, zorder=-32)


# def plot_lightcurve(self, model, axes=None, plot_save=True, plot_show=True, random_models=1000,
#                     posterior=None, use_photon_index_prior=False, outdir='./', plot_magnetar=False):
#     max_l = dict(posterior.sort_values(by=['log_likelihood']).iloc[-1])
#
#     for j in range(int(random_models)):
#         params = dict(posterior.iloc[np.random.randint(len(posterior))])
#         plot_models(parameters=params, axes=axes, alpha=0.05, lw=2, colour='r', model=model,
#                     plot_magnetar=plot_magnetar)
#
#     # plot max likelihood
#     plot_models(parameters=max_l, axes=axes, alpha=0.65, lw=2, colour='b', model=model, plot_magnetar=plot_magnetar)
#
#     self.plot_data(axes=axes)
#
#     label = 'lightcurve'
#     if use_photon_index_prior:
#         label = f"_photon_index_{label}"
#
#     if plot_save:
#         plt.savefig(f"{outdir}{model}{label}.png")
#
#     if plot_show:
#         plt.show()