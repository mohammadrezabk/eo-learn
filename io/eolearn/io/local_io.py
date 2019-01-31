"""
Module containing tasks used for reading and writing to disk
"""

import os.path

import datetime
import rasterio
import numpy as np
from sentinelhub import CRS
from sentinelhub.time_utils import iso_to_datetime

from eolearn.core import SaveToDisk, FeatureType


class ExportToTiff(SaveToDisk):
    """ Task exports specified feature to Geo-Tiff.

    :param feature: Feature which will be exported
    :type feature: (FeatureType, str)
    :param folder: root directory where all Geo-Tiff images will be saved
    :type folder: str
    :param band_indices: Bands to be added to tiff image. Bands are represented by their 0-based index as
    tuple in the form `(start_band, end_band)` or as list in the form `[band_1, band_2,...,band_n]`.
    :type band_indices: tuple or list
    :param date_indices: Dates to be added to tiff image. Dates are represented by their 0-based index as
    tuple in the form `(start_date, end_date)` or a list in the form `[date_1, date_2,...,date_n]`.
    :type date_indices: tuple or list
    :param image_dtype: Type of data to be saved into tiff image
    :type image_dtype: numpy.dtype
    :param no_data_value: Value of pixels of tiff image with no data in EOPatch
    :type no_data_value: int or float
    """

    def __init__(self, feature, folder='.', *, band_indices=[0], date_indices=[0],
                 image_dtype=np.uint8, no_data_value=0):
        super().__init__(folder)

        self.feature = self._parse_features(feature)
        self.band_indices = band_indices
        self.date_indices = date_indices
        self.image_dtype = image_dtype
        self.no_data_value = no_data_value

    def _get_bands_subset(self, array):

        bands = np.array(range(array.shape[-1]))

        if isinstance(self.band_indices, list):
            if [band for band in self.band_indices if not isinstance(band, int)]:
                raise ValueError('Invalid format in {} list, expected integers'.format(self.band_indices))
            array_sub = array[..., np.array(self.band_indices)]
        elif isinstance(self.band_indices, tuple):
            if tuple(map(type, self.band_indices)) != (int, int):
                raise ValueError('Invalid format in {} tuple, expected integers'.format(self.band_indices))
            array_sub = array[..., np.nonzero(np.where(
                (bands >= self.band_indices[0]) & (bands <= self.band_indices[1]), bands, 0))]
        else:
            raise ValueError('Invalid format in {}, expected tuple or list'.format(self.band_indices))

        return array_sub

    def _get_dates_subset(self, array, dates):

        dates = np.array(dates)

        if isinstance(self.date_indices, list):
            if [date for date in self.date_indices if not isinstance(date, int)]:
                raise ValueError('Invalid format in {} list, expected integers'.format(self.date_indices))
            array_sub = array[np.array(self.date_indices)]
        elif isinstance(self.date_indices, tuple):
            if tuple(map(type, self.date_indices)) == (int, int):
                start_date = dates[self.date_indices[0]]
                end_date = dates[self.date_indices[1]]
            elif tuple(map(type, self.date_indices)) == (str, str):
                start_date = iso_to_datetime(self.date_indices[0])
                end_date = iso_to_datetime(self.date_indices[1])
            elif tuple(map(type, self.date_indices)) == (datetime.datetime, datetime.datetime):
                start_date = self.date_indices[0]
                end_date = self.date_indices[1]
            else:
                raise ValueError('Invalid format in {} tuple, expected ints, strings, or datetimes'.format(
                    self.date_indices))
            array_sub = array[np.nonzero(np.where((dates >= start_date) & (dates <= end_date), dates, 0))]
        else:
            raise ValueError('Invalid format in {}, expected tuple or list'.format(self.date_indices))

        return array_sub

    def execute(self, eopatch, *, filename):

        feature_type, feature_name = next(self.feature(eopatch))
        array = eopatch[feature_type][feature_name]

        array_sub = self._get_bands_subset(array)

        if feature_type in [FeatureType.DATA, FeatureType.MASK, FeatureType.SCALAR]:

            array_sub = self._get_dates_subset(array_sub, eopatch.timestamp)

            if feature_type is FeatureType.SCALAR:
                time_dim = array_sub.shape[0]
                band_dim = 1
                width = array_sub.shape[2]
                height = array_sub.shape[1]
            else:
                time_dim = array_sub.shape[0]
                band_dim = array_sub.shape[-1]
                width = array_sub.shape[2]
                height = array_sub.shape[1]
        else:
            time_dim = 1
            band_dim = array_sub.shape[-1]
            width = array_sub.shape[1]
            height = array_sub.shape[0]

        index = time_dim * band_dim
        dst_transform = rasterio.transform.from_bounds(*eopatch.bbox, width=width, height=height)
        dst_crs = {'init': CRS.ogc_string(eopatch.bbox.crs)}

        # Write it out to a file.
        with rasterio.open(os.path.join(self.folder, filename), 'w', driver='GTiff',
                           width=width, height=height,
                           count=index,
                           dtype=self.image_dtype, nodata=self.no_data_value,
                           transform=dst_transform, crs=dst_crs) as dst:
            output_array = array_sub.astype(self.image_dtype)
            output_array = np.moveaxis(output_array, -1, 0).reshape(index, height, width)
            dst.write(output_array)

        return eopatch
