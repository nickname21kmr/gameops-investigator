from __future__ import annotations

import asyncio

from mcp import Client

from gameops_investigator.mcp_server import mcp


def test_mcp_lists_exactly_the_readonly_analysis_surface():
    async def inspect_server():
        async with Client(mcp) as client:
            listed = await client.list_tools()
            names = {tool.name for tool in listed.tools}
            result = await client.call_tool("get_metric_definition", {"metric_name": "d1_retention"})
            return names, result

    names, result = asyncio.run(inspect_server())
    assert names == {
        "get_metric_definition",
        "query_metrics",
        "compare_cohorts",
        "detect_anomalies",
        "draft_incident_report",
    }
    assert not result.is_error
    assert result.structured_content["definition"]["metric_id"] == "d1_retention"

