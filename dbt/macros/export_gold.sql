{#- Export every gold model (except meta export=false) to docs/site/data/<alias>.csv and
    <alias>.json plus _export_manifest.json (model, row count, exported_at_utc, invocation id,
    git commit). The Pages site renders from these files with no build step. Run after
    `dbt build`:  dbt run-operation export_gold [--args "{out_dir: /tmp/x}"] -#}
{% macro export_gold(out_dir='docs/site/data') %}
    {% if execute %}
        {% set gold = [] %}
        {% for node in graph.nodes.values() if node.resource_type == 'model' and 'gold' in node.tags and (node.config.get('meta') or {}).get('export', true) %}
            {% do gold.append(node) %}
        {% endfor %}
        {% set gold = gold | sort(attribute='alias') %}
        {% set manifest_rows = [] %}
        {% for node in gold %}
            {% set relation = adapter.get_relation(database=node.database, schema=node.schema, identifier=node.alias) %}
            {% if relation is none %}
                {{ exceptions.raise_compiler_error("export_gold: " ~ node.schema ~ "." ~ node.alias ~ " does not exist; run dbt build first") }}
            {% endif %}
            {% set csv_path = out_dir ~ '/' ~ node.alias ~ '.csv' %}
            {% set json_path = out_dir ~ '/' ~ node.alias ~ '.json' %}
            {% do run_query("copy (select * from " ~ relation ~ ") to '" ~ csv_path ~ "' (format csv, header true)") %}
            {% do run_query("copy (select * from " ~ relation ~ ") to '" ~ json_path ~ "' (format json, array true)") %}
            {% set n = run_query("select count(*) from " ~ relation).columns[0].values()[0] %}
            {% do manifest_rows.append("select '" ~ node.alias ~ "' as model, " ~ n ~ " as row_count, '" ~ csv_path ~ "' as csv_path, '" ~ json_path ~ "' as json_path") %}
            {% do log("export_gold: " ~ csv_path ~ ", " ~ json_path ~ " (" ~ n ~ " rows)", info=true) %}
        {% endfor %}
        {% set commit = env_var('GITHUB_SHA', '') %}
        {% do run_query(
            "copy (select model, row_count, csv_path, json_path, '" ~ run_started_at.strftime('%Y-%m-%dT%H:%M:%S+00:00') ~ "' as exported_at_utc, '"
            ~ invocation_id ~ "' as invocation_id, '" ~ commit ~ "' as code_commit from ("
            ~ manifest_rows | join(' union all ') ~ ") order by model) to '" ~ out_dir ~ "/_export_manifest.json' (format json, array true)"
        ) %}
        {% do log("export_gold: wrote " ~ out_dir ~ "/_export_manifest.json", info=true) %}
    {% endif %}
{% endmacro %}
