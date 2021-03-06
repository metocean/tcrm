import unittest
import numpy as np
from numpy.testing import assert_almost_equal

import os
import sys
import numpy
from datetime import datetime
import cPickle
import NumpyTestCase
try:
    import pathLocate
except:
    from unittests import pathLocate

# Add parent folder to python path
unittest_dir = pathLocate.getUnitTestDirectory()
sys.path.append(pathLocate.getRootDirectory())

import Utilities.loadData as loadData

class TestInitialPositions(unittest.TestCase):
    """
    Test performance of getInitialPositions()
    """

    def setUp(self):

        self.inputData = cPickle.load(open(os.path.join(unittest_dir,
                                                        'test_data',
                                                        'loadDataInput.pck')))
        #self.indexData = dict(index=self.inputData['index'])
        self.serialData = dict(tcserialno=self.inputData['tcserialno'])
        self.seasonData = dict(season=self.inputData['season'],
                               num=self.inputData['num'])
        self.missingFields = dict(lon=self.inputData['lon'],
                                  lat=self.inputData['lat'])

        self.numData = cPickle.load(open(os.path.join(unittest_dir,
                                                      'test_data',
                                                      'loadDataNumber.pck')))

        self.testIndex = cPickle.load(open(os.path.join(unittest_dir,
                                                        'test_data',
                                                        'loadDataIndex.pck')))
        self.numIndex = cPickle.load(open(os.path.join(unittest_dir,
                                                       'test_data',
                                                       'loadNumIndex.pck')))

    def test_getInitPos_fromSerialNo(self):
        """Test to ensure the function returns correct values based on serial number"""
        idx = loadData.getInitialPositions(self.serialData)
        assert_almost_equal(idx, self.testIndex)

    def test_getInitPos_fromSeason(self):
        """Test to ensure the function returns correct values based on season"""
        idx = loadData.getInitialPositions(self.seasonData)
        assert_almost_equal(idx, self.testIndex)

    def test_getInitPos_fromTCNum(self):
        """Test to ensure the function returns correct values based on TC number"""
        idx = loadData.getInitialPositions(self.numData)
        assert_almost_equal(idx, self.numIndex)

    def test_getInitPos_failure(self):
        """Ensure getInitialPositions fails if insufficient data provided"""
        self.assertRaises(ValueError, loadData.getInitialPositions,
                                      self.missingFields)



class TestDateParsing(unittest.TestCase):
    """
    Test performance of ParseDates()
    """

    def setUp(self):
        """ """
        input_file = open(os.path.join(unittest_dir, 'test_data',
                                       'parseDates.pck'))
        self.dateformat = '%Y-%m-%d %H:%M:%S'
        self.inputData = cPickle.load(input_file)
        self.indicator = cPickle.load(input_file)
        self.year = cPickle.load(input_file)
        self.month = cPickle.load(input_file)
        self.day = cPickle.load(input_file)
        self.hour = cPickle.load(input_file)
        self.minute = cPickle.load(input_file)
        # For testing 'HHMM' formatted times:
        self.hourmin = cPickle.load(input_file)

        input_file.close()
        self.input_dates = dict(date=self.inputData['date'])


    def test_dateInput(self):
        """Test parseDates returns correct values when passed date info"""
        year, month, day, hour, minute, dt = loadData.parseDates(self.input_dates,
                                                             self.indicator)
        assert_almost_equal(year, self.year)
        assert_almost_equal(month, self.month)
        assert_almost_equal(day, self.day)
        assert_almost_equal(hour, self.hour)
        assert_almost_equal(minute, self.minute)

    def test_parseDatesYMDHMInput(self):
        """Test parseDates with year, month, day, hour, minute input"""
        inputdata = dict(year=self.year,
                         month=self.month,
                         day=self.day,
                         hour=self.hour,
                         minute=self.minute)
        year, month, day, hour, minute, dt = loadData.parseDates(inputdata,
                                                             self.indicator)

        assert_almost_equal(year, self.year)
        assert_almost_equal(month, self.month)
        assert_almost_equal(day, self.day)
        assert_almost_equal(hour, self.hour)
        assert_almost_equal(minute, self.minute)

    def test_parseDatesYMDHInput(self):
        """Test parseDates with year, month, day, hourminute (HHMM) input"""
        inputdata = dict(year=self.year,
                         month=self.month,
                         day=self.day,
                         hour=self.hourmin)
        year, month, day, hour, minute, dt = loadData.parseDates(inputdata,
                                                             self.indicator)

        assert_almost_equal(year, self.year)
        assert_almost_equal(month, self.month)
        assert_almost_equal(day, self.day)
        assert_almost_equal(hour, self.hour)
        assert_almost_equal(minute, self.minute)

    def test_ParseDatesNoMinsInput(self):
        """Test parseDates with year, month, day, hour (no minutes) input"""
        inputdata = dict(year=self.year,
                         month=self.month,
                         day=self.day,
                         hour=self.hour)
        year, month, day, hour, minute, dt = loadData.parseDates(inputdata,
                                                             self.indicator)

        assert_almost_equal(year, self.year)
        assert_almost_equal(month, self.month)
        assert_almost_equal(day, self.day)
        assert_almost_equal(hour, self.hour)
        assert_almost_equal(minute, np.zeros((self.hour.size), 'i'))

class TestDateConversion(unittest.TestCase):
    def setUp(self):

        inputFile = open(os.path.join(unittest_dir, 'test_data',
                                      'date2ymhd.pck'))
        self.goodInputDates = cPickle.load(inputFile)
        self.badInputDates = cPickle.load(inputFile)
        self.dateformat = '%Y-%m-%d %H:%M:%S'
        self.outputYear = cPickle.load(inputFile)
        self.outputMonth = cPickle.load(inputFile)
        self.outputDay = cPickle.load(inputFile)
        self.outputHour = cPickle.load(inputFile)
        self.outputMinute = cPickle.load(inputFile)
        inputFile.close()


    def test_date2ymdh(self):
        """Test date2ymdh function"""
        year, month, day, hour, minute, dt = loadData.date2ymdh(self.goodInputDates)
        assert_almost_equal(year, self.outputYear)
        assert_almost_equal(month, self.outputMonth)
        assert_almost_equal(day, self.outputDay)
        assert_almost_equal(hour, self.outputHour)
        assert_almost_equal(minute, self.outputMinute)

    def test_date2ymdhBadFormat(self):
        """Test date2ymdh raises ValueError for poorly formatted year data"""

        datefmt = '%H:%M %m/%d/%y'
        now = datetime.now().strftime(datefmt)
        self.assertRaises(ValueError, loadData.date2ymdh, now, datefmt)

    def test_date2ymdhFormats(self):
        """Test date2ymdh with different input date formats"""

        formats = ['%Y-%m-%d %H:%M:%S',
                   '%Y%m%dT%H%M',
                   '%H:%M %d/%m/%Y',
                   '%H:%M %m/%d/%Y',
                   '%I:%M %p %d/%m/%Y']
        for fmt in formats:
            dates = []
            for d in self.goodInputDates:
                dtobj = datetime.strptime(d, self.dateformat)
                datestr = dtobj.strftime(fmt)
                dates.append(datestr)
            year, month, day, hour, minute, dt = loadData.date2ymdh(dates, fmt)
            assert_almost_equal(self.outputYear, year)
            assert_almost_equal(self.outputMonth, month)
            assert_almost_equal(self.outputDay, day)
            assert_almost_equal(self.outputHour, hour)
            assert_almost_equal(self.outputMinute, minute)

    def test_badData(self):
        """Test date2ymdh raises ValueError for dodgy input date"""
        self.assertRaises(ValueError, loadData.date2ymdh, self.badInputDates)


class TestAgeParsing(unittest.TestCase):

    def setUp(self):
        inputFile = open(os.path.join(unittest_dir, 'test_data',
                                                   'parseAge.pck'))

        self.inputData = cPickle.load(inputFile)
        self.indicator = cPickle.load(inputFile)

        self.outputYear = cPickle.load(inputFile)
        self.outputMonth = cPickle.load(inputFile)
        self.outputDay = cPickle.load(inputFile)
        self.outputHour = cPickle.load(inputFile)
        self.outputMinute = cPickle.load(inputFile)
        inputFile.close()

#    def test_parseAge(self):
#        """Test parseAge function"""
#        year, month, day, hour, minute = loadData.parseAge(self.inputData,
#                                                           self.indicator)
#        assert_almost_equal(self.outputYear, year)
#        assert_almost_equal(self.outputMonth, month)
#        assert_almost_equal(self.outputDay, day)
#        assert_almost_equal(self.outputHour, hour)
#        assert_almost_equal(self.outputMinute, minute)


class TestTimeDeltas(unittest.TestCase):

    def setUp(self):
        inputFile = open(os.path.join(unittest_dir, 'test_data',
                                      'getTimeDelta.pck'))
        self.inputYear = cPickle.load(inputFile)
        self.inputMonth = cPickle.load(inputFile)
        self.inputDay = cPickle.load(inputFile)
        self.inputHour = cPickle.load(inputFile)
        self.inputMinute = cPickle.load(inputFile)
        self.outputDT = cPickle.load(inputFile)
        inputFile.close()

    def test_getTimeDelta(self):
        """Test getTimeDelta function"""
        dt = loadData.getTimeDelta(self.inputYear,
                                   self.inputMonth,
                                   self.inputDay,
                                   self.inputHour,
                                   self.inputMinute)

        assert_almost_equal(dt, self.outputDT)

    def test_getTimeDeltaBadInput(self):
        """Test getTimeDelta raises ValueError on bad input"""
        inputMonth = self.inputMonth
        inputMonth[345] = 13

        badMonthArgs = [self.inputYear, inputMonth, self.inputDay,
                        self.inputHour, self.inputMinute]

        inputYear = self.inputYear
        inputYear[126] = -1
        badYearArgs = [inputYear, self.inputMonth, self.inputDay,
                        self.inputHour, self.inputMinute]

        self.assertRaises(ValueError, loadData.getTimeDelta,
                          *badMonthArgs)
        self.assertRaises(ValueError, loadData.getTimeDelta,
                          *badYearArgs)

class TestTime(unittest.TestCase):

    def setUp(self):
        inputFile = open(os.path.join(unittest_dir, 'test_data',
                                      'getTime.pck'))
        self.inputYear = cPickle.load(inputFile)
        self.inputMonth = cPickle.load(inputFile)
        self.inputDay = cPickle.load(inputFile)
        self.inputHour = cPickle.load(inputFile)
        self.inputMinute = cPickle.load(inputFile)
        self.outputTime = cPickle.load(inputFile)
        inputFile.close()

    def test_getTime(self):
        """Test getTime function"""
        time = loadData.getTime(self.inputYear,
                                self.inputMonth,
                                self.inputDay,
                                self.inputHour,
                                self.inputMinute)

        assert_almost_equal(time, self.outputTime)

    def test_getTimeBadInput(self):
        """Test getTime raises ValueError on bad input"""
        inputMonth = self.inputMonth
        inputMonth[345] = 13

        badMonthArgs = [self.inputYear, inputMonth, self.inputDay,
                        self.inputHour, self.inputMinute]

        inputYear = self.inputYear
        inputYear[126] = -1
        badYearArgs = [inputYear, self.inputMonth, self.inputDay,
                        self.inputHour, self.inputMinute]

        self.assertRaises(ValueError, loadData.getTime,
                          *badMonthArgs)
        self.assertRaises(ValueError, loadData.getTime,
                          *badYearArgs)

class TestJulianDays(unittest.TestCase):

    def setUp(self):
        inputFile = open(os.path.join(unittest_dir, 'test_data',
                                      'julianDays.pck'))
        self.inputYear = cPickle.load(inputFile)
        self.inputMonth = cPickle.load(inputFile)
        self.inputDay = cPickle.load(inputFile)
        self.inputHour = cPickle.load(inputFile)
        self.inputMinute = cPickle.load(inputFile)
        self.outputJdays = cPickle.load(inputFile)
        inputFile.close()

    def test_julianDays(self):
        """Test julianDays function"""
        jday = loadData.julianDays(self.inputYear,
                                   self.inputMonth,
                                   self.inputDay,
                                   self.inputHour,
                                   self.inputMinute)

        assert_almost_equal(jday, self.outputJdays)

    def test_julianDaysBadInput(self):
        """Test julianDays raises ValueError on bad input"""
        inputMonth = self.inputMonth
        inputMonth[345] = 13

        badMonthArgs = [self.inputYear, inputMonth, self.inputDay,
                        self.inputHour, self.inputMinute]

        inputYear = self.inputYear
        inputYear[126] = -1
        badYearArgs = [inputYear, self.inputMonth, self.inputDay,
                        self.inputHour, self.inputMinute]

        self.assertRaises(ValueError, loadData.julianDays,
                          *badMonthArgs)
        self.assertRaises(ValueError, loadData.julianDays,
                          *badYearArgs)

class TestLoadingTrackFiles(unittest.TestCase):

    def setUp(self):
        self.config_file = os.path.join(unittest_dir, 'test_data',
                                      'test.ini')
        self.track_file = os.path.join(unittest_dir, 'test_data',
                                      'test_trackset.csv')
        self.source = 'TESTSOURCE'

        inputFile = open(os.path.join(unittest_dir, 'test_data',
                                      'loadTrackFile.pck'))
        self.trackData = cPickle.load(inputFile)

#class TestFilterPressure(unittest.TestCase):
#
#    def setUp(self):
#        inputFile = open(os.path.join(unittest_dir, 'test_data',
#                                      'filterPressure.pck'))
#        self.inputdata = cPickle.load(inputFile)
#        self.outputdata = cPickle.load(inputFile)
#        inputFile.close()
#
#    def test_filterPressure(self):
#        """Test filterPressure function"""
#        result = loadData.filterPressure(self.inputdata)
#        assert_almost_equal(result, self.outputdata, decimal=5)

if __name__ == "__main__":
    unittest.main()
