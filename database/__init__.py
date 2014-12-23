"""
:mod:`database` -- build, update and query a database of hazard and events
==========================================================================

.. module:: database
    :synopsis: Build, update, query a database for hazard and event
               information.

.. moduleauthor:: Craig Arthur <craig.arthur@ga.gov.au>

The :class:`HazardDatabase` class provides methods to create and
populate a :mod:`sqlite3` database that holds location-specific
information on the synthetic events and the hazard (return period wind
speeds). This database allows users to identify events that generate
wind speeds corresponding to some threshold, such as a return period
wind speed, at each location in the domain, which could then be
selected for more detailed modelling. 

TODO: Upgrade to spatial database (e.g. SpatiaLite) to better handle
geometries & projected location data.

"""

import os
import logging
import sqlite3
from datetime import datetime
import unicodedata

from os.path import join as pjoin

from shapely.geometry import Point
from netCDF4 import Dataset
import numpy as np

from Utilities.config import ConfigParser
from Utilities.files import flModDate
from Utilities.maputils import find_index
from Utilities.loadData import loadTrackFile
from Utilities.track import loadTracksFromFiles

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())

# Stations - we assume a geographic coordinate system:
tblLocationsDef = ("CREATE TABLE IF NOT EXISTS tblLocations "
                  "(locId integer PRIMARY KEY, locCode text, "
                  "locName text, locType text, locLon real, "
                  "locLat real, locElev real, locCountry text, "
                  "locSource text, Comments text, "
                  "dtCreated timestamp)")

# Events:
tblEventsDef = ("CREATE TABLE IF NOT EXISTS tblEvents "
                "(eventNumber integer PRIMARY KEY, eventId text, "
                "eventFile text, eventTrackFile text, "
                "eventMaxWind real, eventMinPressure real, "
                "dtTrackFile timestamp, dtWindfieldFile timestamp, "
                "tcrmVersion text, Comments text, dtCreated timestamp)")

#Station wind speed from events:
tblWindSpeedDef = ("CREATE TABLE IF NOT EXISTS tblWindSpeed "
                   "(locId integer, eventNumber integer, wspd real, umax real, "
                   "vmax real, pmin real, Comments text, "
                   "dtCreated timestamp)")

# Station hazard levels:
tblHazardDef = ("CREATE TABLE IF NOT EXISTS tblHazard "
                "(locId integer, returnPeriod real, wspd real, "
                " wspdUpper real, wspdLower real, loc real, "
                "scale real, shape real, tcrmVersion text, "
                "dtHazardFile timestamp, Comments text, "
                "dtCreated timestamp)")

# Proximity of tracks to stations:
tblTracksDef = ("CREATE TABLE IF NOT EXISTS tblTracks "
                "(locId integer, eventNumber integer, distClosest real, "
                "prsClosest real, dtClosest timestamp, Comments text, "
                "dtCreated timestamp)")

# Insert locations:
insLocations = "INSERT INTO tblLocations VALUES (?,?,?,?,?,?,?,?,?,?,?)"

# Insert event record:
insEvents = "INSERT INTO tblEvents VALUES (?,?,?,?,?,?,?,?,?,?,?)"

# Insert wind speed record:
insWindSpeed = "INSERT INTO tblWindSpeed VALUES (?,?,?,?,?,?,?,?)"

# Insert hazard record:
insHazard = "INSERT INTO tblHazard VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"

# Insert track record:
insTrack = "INSERT INTO tblTracks VALUES (?,?,?,?,?,?,?)"

# Select locations within domain:
selectLocations = ("SELECT * FROM tblLocations WHERE "
                   "locLon >= ? and locLon <= ? and "
                   "locLat >= ? and locLat <= ?")

# Select locId, locLon & locLat from the subset of locations:
selectLocLonLat = "SELECT locId, locLon, locLat FROM tblLocations "

def windfieldAttributes(ncfile):
    """
    Extract the required attributes from a netCDF file.

    :param str ncfile: Path to a valid netCDF file created by TCRM.

    :returns: A tuple containing the track filename, file modification date,
              TCRM version, minimum pressure and maximum wind, stored as
              global attributes in the netCDF file.
        
    """
    ncobj = Dataset(ncfile, 'r')
    trackfile = getattr(ncobj, 'track_file')
    trackfiledate = getattr(ncobj, 'track_file_date')
    trackfiledate = datetime.strptime(trackfiledate, '%Y-%m-%d %H:%M:%S')
    tcrm_version = getattr(ncobj, 'tcrm_version')
    trackfile = unicodedata.normalize("NFKD", trackfile).encode('utf-8', 'ignore')
    trackfile = os.path.basename(trackfile)
    tcrm_version = unicodedata.normalize("NFKD", tcrm_version).encode('utf-8', 'ignore')
    slpobj = ncobj.variables['slp']
    minslp = getattr(slpobj, 'actual_range')[0]

    vmaxobj = ncobj.variables['vmax']
    maxwind = getattr(vmaxobj, 'actual_range')[1]
    ncobj.close()
    return (trackfile, trackfiledate, tcrm_version, minslp, maxwind)

def singleton(cls):
    instances = {}

    def getinstance(*args, **kwargs):
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]
    return getinstance


@singleton
class HazardDatabase(sqlite3.Connection):
    """
    Create and update a database of locations, events, hazard, wind speed and tracks.

    :param str configFile: Path to the simulation configuration file.

    """

    def __init__(self, configFile):
        self.configFile = configFile

        config = ConfigParser()
        config.read(configFile)

        self.inputPath = "./input"
        self.outputPath = config.get('Output', 'Path')
        self.windfieldPath = pjoin(self.outputPath, 'windfield')
        self.trackPath = pjoin(self.outputPath, 'tracks')
        self.hazardPath = pjoin(self.outputPath, 'hazard')
        self.domain = config.geteval('Region', 'gridLimit')
        self.hazardDB = pjoin(self.outputPath, 'hazard.db')
        self.locationDB = pjoin(self.outputPath, 'locations.db')
        
        sqlite3.Connection.__init__(self, self.hazardDB,
                                    detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)

        self.exists = True
        
        import atexit
        atexit.register(self.close)

    def createDatabase(self):
        """
        Create the database.

        """
        log.info("Building the hazard database...")
        self.createTable('tblLocations', tblLocationsDef)
        self.createTable('tblEvents', tblEventsDef)
        self.createTable('tblWindSpeed', tblWindSpeedDef)
        self.createTable('tblHazard', tblHazardDef)
        self.createTable('tblTracks', tblTracksDef)
        self.exists = True
        self.commit()
        return

    def createTable(self, tblName, tblDef):
        """
        Create a table.

        :param tblName: Table name.
        :param tblDef: Table definition.

        """
        log.info("Creating table %s" % tblName)
        log.debug("Executing statement: %s" % tblDef)
        try:
            self.execute(tblDef)
            self.commit()
        except sqlite3.Error as e:
            log.exception("Cannot create table %s: %s" % (tblName, e.args[0]))
            raise
        
    def setLocations(self):
        """
        Populate _tblLocations_ in the hazard database with all
        locations from the default locations database that lie
        within the simulation domain.

        """
        
        conn = sqlite3.connect(self.locationDB,
                               detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)
        c = conn.execute(selectLocations, (self.domain['xMin'],
                                           self.domain['xMax'],
                                           self.domain['yMin'],
                                           self.domain['yMax']) )

        locations = c.fetchall()
        conn.close()
        if len(locations) >= 1:
            self.executemany(insLocations, locations)
            self.commit()
        else:
            log.info("No locations returned")

    def getLocations(self):
        """
        Retrieve all locations stored in the hazard database.

        :returns: List of tuples containing location id, longitude and latitude.
        
        """
        try:
            c = self.execute("SELECT locId, locLon, locLat FROM tblLocations")
        except sqlite.Error as e:
            log.exception("Cannot retrieve locations from tblLocations: %s" % e)
            raise
        else:
            locations = c.fetchall()
            
        return locations
    
    def generateEventTable(self):
        """
        Populate _tblEvents_ with the details of the synthetic events
        generated in the simulation. This table only holds the
        metadata of the events. At this time, since TCRM generates
        annual event sets, this table only stores details of the
        annual event set. Future versions can hold additional metadata
        about each individual synthetic TC event.

        """
        fileList = os.listdir(self.windfieldPath)
        files = [pjoin(self.windfieldPath, f) for f in fileList]
        files = [f for f in files if os.path.isfile(f)]
        
        params = []
        for n, f in enumerate(sorted(files)):
            log.debug("Processing {0}".format(f))
            si = os.stat(f)
            dtWindfieldFile = datetime.fromtimestamp(int(si.st_mtime))
            trackfile, dtTrackFile, tcrm_version, minslp, maxwind = \
                windfieldAttributes(f)
            params.append(("%06d"%n, "%06d"%n, os.path.basename(f), trackfile,
                           float(maxwind), float(minslp), dtTrackFile,
                           dtWindfieldFile, tcrm_version, "", datetime.now()))

        try:
            self.executemany(insEvents, params)
        except sqlite3.Error as e:
            log.exception("Cannot insert records into tblEvents: %s" % e.args[0])
            raise
        else:
            self.commit()

    def processEvents(self):
        """
        Process the events (wind fields) for each location within the
        model domain and populate _tblWindSpeed_. This will store the
        modelled wind speed (or the missing value) at each grid point,
        from each synthetic event.

        """

        fileList = os.listdir(self.windfieldPath)
        files = [pjoin(self.windfieldPath, f) for f in fileList]
        files = [f for f in files if os.path.isfile(f)]

        locations = self.getLocations()

        for n, f in enumerate(sorted(files)):
            log.debug("Processing {0}".format(f))
            eventId = "%06d" % n
            ncobj = Dataset(f)
            lon = ncobj.variables['lon'][:]
            lat = ncobj.variables['lat'][:]
        
            vmax = ncobj.variables['vmax'][:]
            ua = ncobj.variables['ua'][:]
            va = ncobj.variables['va'][:]
            pmin = ncobj.variables['slp'][:]
            params = []
        
            for loc in locations:
                locId, locLon, locLat = loc
                i = find_index(lon, locLon)
                j = find_index(lat, locLat)
                locVm = vmax[j, i]
                locUa = ua[j, i]
                locVa = va[j, i]
                locPr = pmin[j, i]
                locParams = (locId, eventId, float(locVm), float(locUa),
                             float(locVa), float(locPr), " ", datetime.now())

                params.append(locParams)

            try:
                self.executemany(insWindSpeed, params)
            except sqlite3.Error as e:
                log.exception("Cannot insert records into tblWindSpeed: %s" % e.args[0])
                raise
            else:
                self.commit()

    def processHazard(self):
        """
        Update _tblHazard_ with the return period wind speed data.

        """

        locations = self.getLocations()

        ncobj = Dataset(pjoin(self.hazardPath, 'hazard.nc'))
    
        try:
            tcrm_version = getattr(ncobj, 'tcrm_version')
        except AttributeError:
            log.info("Missing tcrm_version attribute from {0}".format(hazardFile))
            tcrm_version = ''

        si = os.stat(pjoin(self.hazardPath, 'hazard.nc'))
        dtHazardFile = datetime.fromtimestamp(int(si.st_mtime))
        lon = ncobj.variables['lon'][:]
        lat = ncobj.variables['lat'][:]
        years = ncobj.variables['years'][:]

        wspd = ncobj.variables['wspd'][:]
        wspdUpper = ncobj.variables['wspdupper'][:]
        wspdLower = ncobj.variables['wspdlower'][:]
        locationParam = ncobj.variables['loc'][:]
        scaleParam = ncobj.variables['scale'][:]
        shpParam = ncobj.variables['shp'][:]

        params = []
        for k, year in enumerate(years):
            for loc in locations:
                locId, locLon, locLat = loc
                i = find_index(lon, locLon)
                j = find_index(lat, locLat)
                locWspd = wspd[k, j, i]
                locUpper = wspdUpper[k, j, i]
                locLower = wspdLower[k, j, i]

                locLoc = locationParam[j, i]
                locScale = scaleParam[j, i]
                locShp = shpParam[j, i]

                locParams = (locId, int(year), float(locWspd), float(locUpper),
                             float(locLower), float(locLoc), float(locScale),
                             float(locShp), tcrm_version, dtHazardFile, "",
                             datetime.now())

                params.append(locParams)

        try:
            self.executemany(insHazard, params)
        except sqlite3.Error as e:
            log.exception("Cannot insert records into tblHazard: %s" % e.args[0])
            raise
        else:
            self.commit()

    def processTracks(self):
        """
        Populate tblTracks with the details of tracks and their proximity to
        the locations in the domain.

        """
        locations = self.getLocations()
        points = [Point(loc[1], loc[2]) for loc in locations]
        trackPath = pjoin(self.outputPath, 'tracks')
        files = os.listdir(trackPath)
        trackfiles = [pjoin(trackPath, f) for f in files if f.startswith('tracks')]
        tracks = loadTracksFromFiles(sorted(trackfiles))
        params = []
        for track in tracks:
            if len(track.data) == 0:
                continue
            distances = track.minimumDistance(points)
            for (loc, dist) in zip(locations, distances):
                locParams = (loc[0], "%d-%d"%(track.trackId), dist, None, None, "",
                             datetime.now())

                params.append(locParams)

        try:
            self.executemany(insTrack, params)
        except sqlite3.Error as e:
            log.exception("Cannot insert records into tblTracks: %s" % e.args[0])
            raise
        else:
            self.commit()
    
        
def buildLocationDatabase(location_db, location_file, location_type='AWS'):
    """
    Build a database of locations, using a point shape file of the locations.
    The locations *must* be represented in a geographic coordinate system.

    This version is hard coded to work with the `stationlist` file that is
    provided with the RIP4 graphics package, which has in turn been stored
    as a shapefile.

    Users can augment the basic location database with their own data, noting
    the schema for ``tblLocations``.
    
    :param str location_db: Path to the location database.
    :param str location_file: Path to a shape file containing location data.

    :returns: List of tuples containing location Id, name, longitude,
              latitude, elevation, country, comments and current datetime.

    TODO: Build a way to ingest user-defined list of fields that correspond
          to the required fields in tblLocations. e.g. using a mappings dict::
    
              mappings = {
                  'locCode' : 'WMO',
                  'locName' : 'Place'
                  'locCountry' : 'Cou'
                  'locElev' : 'Elevation'
                  'Comments' : 'ICAO'
                  }

              columns = ('locCode', 'locName', 'locCountry', 'locElev', 'Comments')

              for col in columns:
                  if mappings.has_key(col):
                      field = shpGetField(location_file, mappings[col])
                      
    """
    
    from Utilities.shptools import shpReadShapeFile
    locations = []
    vertices, records = shpReadShapeFile(location_file)

    # Perform a check that locations are in geographic coordinates:
    lons = []
    lats = []
    for v in vertices.values():
        lon, lat = v[0]
        lons.append[lon]
        lats.append[lat]

    msg=("Location shapefile must be in a geograpic coordinate system "
         "(i.e. it must have lat/lon vertices). It looks like this "
         "one has vertices in map projection coordinates. You can convert the "
         "shapefile to geographic coordinates using the shpproj utility from "
         "the shapelib tools (http://shapelib.maptools.org/shapelib-tools.html)")

    if max(lons) > 721. or min(lons) < -721. or max(lats) > 91. or min(lats) < -91:
        raise ValueError(msg)

    # Prepare entries:
    for v, r in zip(vertices.values(), records):
        locLon, locLat = v[0]
        locLon = np.mod(locLon, 360.)
        locCode = str(r[0])
        locName = r[2]
        locCountry = r[4]
        locElev = r[7]
        locComment = r[1]
        locations.append((None, locCode, locName, location_type,
                          locLon, locLat, locElev, locCountry,
                          os.path.basename(location_file),
                          locComment, datetime.now()))

    locdb = sqlite3.connect(location_db, detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)
    locdb.execute(tblLocationsDef)
    locdb.executemany(insLocations, locations)
    locdb.commit()
    locdb.close()

def locationRecordsExceeding(hazard_db, locId, windSpeed):
    """
    Select all records where the wind speed at the given location is
    greater than some threshold. 
    
    :param hazard_db: :class:`HazardDatabase` instance.
    :param int locId: Location identifier.
    :param float windSpeed: Select all records where the wind speed
                            at the given location is greater than
                            this value.

    :returns: List of tuples, each tuple contains the name, longitude
              & latitude of the location, the wind speed of the
              record, the event Id and the event file that holds the
              event that generated the wind speed.
    
    Example::
    
        >>> db = HazardDatabase(configFile)
        >>> locId = 00001
        >>> records = locationRecordsExceeding(db, locId, 47.)
        
    """

    query = ("SELECT l.locId, l.locName, w.wspd, w.eventNumber, "
             "e.eventFile "
             "FROM tblLocations l "
             "INNER JOIN tblWindSpeed w ON l.locId = w.locId "
             "JOIN tblEvents e ON e.eventNumber = w.eventNumber "
             "WHERE w.wspd > ? and l.locId = ? "
             "ORDER BY w.wspd ASC" )

    c = hazard_db.execute(query, (windSpeed, locId,))
    results = c.fetchall()
    return results

def locationRecords(hazard_db, locId):
    """
    Select all wind speed records for a given location.

    :param hazard_db: :class:`HazardDatabase` instance.
    :param int locId: Location identifier.

    """
    
    query = ("SELECT l.locId, l.locName, w.wspd, w.eventNumber "
             "FROM tblLocations l "
             "INNER JOIN tblWindSpeed w "
             "ON l.locId = w.locId "
             "JOIN tblEvents e ON e.eventNumber = w.eventNumber "
             "WHERE l.locId = ? ORDER BY w.wspd ASC")
    c = hazard_db.execute(query, (locId,))
    results = c.fetchall()
    return results
    
def locationPassage(hazard_db, locId, distance=50):
    """
    Select all records from tblTracks that pass within a defined
    distance of the given location

    :param hazard_db: :class:`HazardDatabase` instance.
    :param int locId: Location identifier.
    :param distance: Distance threshold (in kilometres).

    Example::

        >>> db = HazardDatabase(configFile)
        >>> locId = 000001
        >>> records = locationPassage(db, locId, 50)

    """

    query = ("SELECT l.locId, l.locName, t.eventNumber, t.distClosest, "
             "w.wspd, e.eventFile FROM tblLocations l "
             "INNER JOIN tblTracks t "
             "ON l.locId = t.locId "
             "JOIN tblWindSpeed w on w.eventNumber = t.eventNumber "
             "JOIN tblEvents e on e.eventNumber = t.eventNumber "
             "WHERE t.distClosest < ? and l.locId = ?")
    c = hazard_db.execute(query, (locId, distance))
    results = c.fetchall()
    return results

def locationReturnPeriodEvents(hazard_db, locId, return_period):
    """
    Select all records from tblEvents where the wind speed is
    greater than the return period wind speed for the given return period.

    :param hazard_db: :class:`HazardDatabase` instance.
    :param int locId: Location identifier.
    :param int return_period: Nominated return period.

    """

    query = ("SELECT l.locId, h.wspd FROM tblLocations l "
             "INNER JOIN tblHazard h ON l.locId = h.locId "
             "WHERE h.returnPeriod = ? and l.locId = ?")
    c = hazard_db.execute(query, (return_period, locId))
    r = c.fetchall()
    return_level = r[0][1]
    results = locationRecordsExceeding(hazard_db, locId, return_level)

    return results

def locationAllReturnLevels(hazard_db, locId):
    """
    Select all return level wind speeds (including upper and lower
    confidence intervals) for a selected location.

    :param hazard_db: :class:`HazardDatabase` instance.
    :param int locId: Location identifier.

    """

    query = ("SELECT l.locId, l.locName, h.returnPeriod, h.wspd, "
             "h.wspdLower, h.wspdUpper "
             "FROM tblLocations t INNER JOIN tblHazard h "
             "ON l.locId = h.locId "
             "WHERE l.locIf = ? "
             "ORDER BY h.returnPeriod")

    c = hazard_db.execute(query, (locId,))
    results = c.fetchall()

    return results
