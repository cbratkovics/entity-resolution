{{ config(materialized='table') }}

-- artifacts/models/<version>/test_predictions.csv, typed. model_version comes from the path.
select
    filename as source_file,
    regexp_extract(filename, 'models/([^/]+)/test_predictions\.csv$', 1) as model_version,
    cast(record_id as varchar) as record_id,
    cast(batch as integer) as batch,
    cast(batch as integer) as batch,
    cast(source as varchar) as source,
    cast(record_name as varchar) as record_name,
    cast(team as varchar) as team,
    cast(candidate as varchar) as candidate,
    cast(prediction as double) as prediction,
    cast(prediction_floor as double) as prediction_floor,
    cast(prediction_ceiling as double) as prediction_ceiling,
    cast(actual as double) as actual
from {{ source('repo_files', 'predictions_test') }}
