import argparse
import yaml
import glob
import os
import zipfile
import geopandas as gpd
import pandas as pd
from shapely.wkt import loads


cities_and_counties = yaml.load(open("cities_and_counties.yaml"))


def unzip_file(fname, out_dir):
    zip_ref = zipfile.ZipFile(fname, 'r')
    zip_ref.extractall(out_dir)
    zip_ref.close()

# read all the general plan spatial data in and merge it
def merge_gp_spatial_data(cities_and_counties, path_format="{}/{}/*.geojson"):
    gdfs = []
    strings = []
    for county, cities in cities_and_counties.items():
        for city in cities:
            for geojson in glob.glob(path_format.format(county, city)):
                s = "'{}': 'http://oaklandanalytics.github.io/badata/{}',".format(city.replace('_', ' ').title(), geojson)
                strings.append(s)
                print s
                gdf = gpd.GeoDataFrame.from_file(geojson)
                gdf["city"] = city.replace('_', ' ').title()
                gdf["priority"] = 2 if "plu" in geojson else 1
                gdfs.append(gdf)

    strings.sort()
    for string in strings:
        print string
    return gpd.GeoDataFrame(pd.concat(gdfs))

# we store general plan data in a set of shapefiles and zoning attributes in
# a csv this method tells us which join keys are missing from each dataset
def diagnose_merge(df, gdf):
    print "Number of records in zoning data that have a shape to join to:"
    df["zoning_id"] = df.id  # need to rename so names don't clash in merge

    df2 = pd.merge(df, gdf,
                   left_on=["city", "name"],
                   right_on=["city", "general_plan_name"])

    missing = df[~df.zoning_id.isin(df2.zoning_id)]
    print "{} missing zoning ids (data written to missing_zoning_ids.csv".\
        format(len(missing))
    missing.to_csv("missing_zoning_ids.csv", index=False)


# pass in a shapefile of general plan data and join in to each county
# shapefile in turn
def merge_parcels_and_gp_data(gp_data):
    joined_counties = []
    for county, cities in cities_and_counties.items():
        print "Joining parcels to general plan data for {}".format(county)

        geopath = "{}/{}_parcels_geom.shp".format(county, county)
        if not os.path.exists(geopath):
            unzip_file(geopath.replace("shp", "zip"), os.path.join(".", county))

        csvpath = "{}/{}_parcels.csv".format(county, county)
        if not os.path.exists(csvpath):
            unzip_file(csvpath.replace("csv", "zip"), os.path.join(".", county))

        parcel_attributes = pd.read_csv(csvpath, low_memory=False)
        parcels = gpd.GeoDataFrame.from_file(geopath)
        # join attributes to shapes
        parcels = gpd.GeoDataFrame(pd.merge(parcels, parcel_attributes, on="gid"))
        parcels.crs = {'init': u'epsg:4326'}
        parcels["parcel_id"] = parcels.gid
        parcels["geometry"] = parcels.centroid
        print "  joining {} rows".format(len(parcels))

        print "Joining to TAZs"
        zones = gpd.GeoDataFrame.from_file("data/tazs.json")
        zones.crs = {'init': u'epsg:4326'}
        zones["zone_id"] = zones.ZONE_ID
        ret = gpd.sjoin(parcels, zones, how="left", op="within")
        # just keep the columns that we had before plus zone_id
        # spatial join in the next step was breaking otherwise
        ret = ret[list(parcels.columns) + ["zone_id"]]

        print "Joining to GP data"
        ret = gpd.sjoin(ret, gp_data, how="left", op="within")

        # sort by prioity and drop duplicates, 1 priority is higher than 2 etc
        ret = ret.sort_values("priority").drop_duplicates(subset=["parcel_id"])
        ret = gpd.GeoDataFrame(ret)  # make spatial again

        ret["x"] = [shp.x for shp in ret.geometry]
        ret["y"] = [shp.y for shp in ret.geometry]

        ret = ret.drop(["geometry", "gid", "id", "index_right"], axis=1)
        joined_counties.append(ret)

    return pd.concat(joined_counties)


parser = argparse.ArgumentParser(description='Run Bay Area data script.')

parser.add_argument('--mode', action='store', dest='mode',
                    help='which mode to run (see code for mode options)')

options = parser.parse_args()

MODE = options.mode

if MODE == "merge_gp_data":
    print "Reading geojson data by juris"
    gdf = merge_gp_spatial_data(cities_and_counties)
    print "Writing general plan data as csvfile"
    # writing to csv makes reading the attributes in very fast
    # shapefiles take a long time to read in python
    gdf.to_csv("merged_general_plan_data.csv", index=False)

elif MODE == "merge_parcels_and_gp_data":
    print "Merging parcels and general plan data"
    df = pd.read_csv("merged_general_plan_data.csv")
    print "Converting geocsv"
    # convert shapes from text
    df["geometry"] = [loads(shp) for shp in df.geometry]
    gdf = gpd.GeoDataFrame(df)
    gdf.crs = {'init': u'epsg:4326'}
    print "Converted geocsv to geodataframe"
    df = merge_parcels_and_gp_data(gdf)
    df.to_csv("parcels_joined_to_general_plans.csv", index=False)

    for name, grp in df.groupby("zone_id"):
        grp.to_csv("output/taz{}_zoning.csv".format(int(name)), index=False)

elif MODE == "diagnose_merge":
    print "Reading gp data"
    gdf = pd.read_csv("merged_general_plan_data.csv")
    df = pd.read_csv("zoning_lookup.csv")
    # this file is not in this repo - it should be copied from the
    # bayarea_urbansim repo soon we will generate a new zoning-parcel
    # relationship file using this data
    df2 = pd.read_csv("2015_12_21_zoning_parcels.csv")
    # drop rows which aren't linked to parcels
    df = df[df.id.isin(df2.zoning_id)]
    df["Parcel Count"] = df2.zoning_id.value_counts().loc[df.id].values
    diagnose_merge(df, gdf)

else:
    print "Must pick a mode.  Options include merge_gp_data, diagnose_merge..."
