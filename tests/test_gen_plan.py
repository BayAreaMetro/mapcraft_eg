import pandas as pd
import pytest
import os
import json


counties = ['alameda', 'contra_costa', 'marin', 'napa', 'san_mateo',
            'santa_clara', 'solano', 'sonoma', 'san_francisco']
jurises = [(d, c) for c in counties for d in os.listdir(c)]
# jurises = [("petaluma", "sonoma")]


@pytest.mark.parametrize("juris,county", jurises)
def test_csv_and_geojson_join(juris, county):

    dirname = os.path.join(county, juris, 'general_plan')
    csvname = os.path.join(dirname, '%s.csv' % juris)
    geojsonname = os.path.join(dirname, '%s.geojson' % juris)

    df = pd.read_csv(csvname, index_col="name")

    shapes = json.load(open(geojsonname))
    shapes = [f["properties"] for f in shapes["features"]]

    # only san francisco really has lots of general plan shapes
    # other cities are using parcels as their general plan shapes,
    # which need to be dissolved
    assert len(shapes) < 2000 or juris in ["san_francisco", "san_jose"]

    plan_names = pd.DataFrame.from_records(shapes).general_plan_name
    empty_names = plan_names[plan_names.isnull()]

    # general plan name is missing on shapes
    assert len(empty_names) == 0

    unique_plan_names = plan_names.unique()

    if not df.index.is_unique:
        print pd.Series(df.index).value_counts().head()
    # duplicated general plan names in the csv
    assert df.index.is_unique

    # all the names on the shapes exist in the csv file
    assert len(df.loc[unique_plan_names]) == len(unique_plan_names)


@pytest.mark.parametrize("juris,county", jurises)
def test_csv_schema(juris, county):

    dirname = os.path.join(county, juris, 'general_plan')
    csvname = os.path.join(dirname, '%s.csv' % juris)

    df = pd.read_csv(csvname, index_col="name")

    cols = ("city,max_far,max_height,max_dua,max_du_per_parcel,HS,HT,HM" +\
           ",OF,HO,SC,IL,IW,IH,RS,RB,MR,MT,ME").split(',')
    for col in cols:
        # check column names
        assert col in df.columns

    # types should be right
    assert df.max_far.dtype == "float"
    assert df.max_dua.dtype == "float"
    assert df.max_height.dtype in ["float", "int"]
    assert df.max_du_per_parcel.dtype in ["float", "int"]

    # buildings types should be on or off
    for col in "HS,HT,HM,OF,HO,SC,IL,IW,IH,RS,RB,MR,MT,ME".split(","):
        ind = list(df[col].value_counts().index)
        assert ind == [0, 1] or ind == [1, 0] or ind == [1.0] \
            or ind == [0] or ind == []

    # values should be in right ranges
    assert df.max_far.fillna(0).min() >= 0
    assert df.max_far.fillna(0).max() <= 30
    assert df.max_height.fillna(0).min() >= 0
    assert df.max_height.fillna(0).max() <= 1000
    assert df.max_dua.fillna(0).min() >= 0
    assert df.max_dua.fillna(0).max() <= 350
    assert df.max_du_per_parcel.fillna(0).min() >= 0
    assert df.max_du_per_parcel.fillna(0).max() <= 10
        
