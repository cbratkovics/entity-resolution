-- Grain: one row per source (side B Discogs, side A MusicBrainz): the dump each side of the
-- current run was loaded from, with its hash, date and licence URL.
select
    cast(s.name as varchar) as source,
    cast(s.side as varchar) as side,
    cast(s.dump_filename as varchar) as dump_filename,
    cast(s.dump_bytes as bigint) as dump_bytes,
    cast(s.dump_sha256 as varchar) as dump_sha256,
    cast(s.dump_date as varchar) as dump_date,
    cast(s.download_url as varchar) as download_url,
    cast(s.licence_url as varchar) as licence_url
from {{ ref('brz_manifest_sources') }} as s
