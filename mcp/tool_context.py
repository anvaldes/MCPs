import time
import inspect
from zoneinfo import ZoneInfo
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from utils import save_json_to_gcs
from request_context import current_user


@asynccontextmanager
async def tool_context(mcp_name: str, inputs: dict):
    """
    Context manager que estandariza el logging de cada tool MCP.

    Infiere el nombre de la tool a partir del nombre de la función llamadora,
    registra latencia, usuario, fecha, inputs, output y error en GCS.

    Uso:
        async with tool_context(SERVICE_NAME, {"input": input}) as ctx:
            ctx.result = f"transformación: {input[::-1]}"
    """

    # ── Inferir nombre de la tool desde el call stack ──────────────────────
    caller = inspect.stack()[2].function   # [0]=tool_context, [1]=__aenter__, [2]=tool fn
    tool = caller

    # ── Fecha y prefijo GCS ────────────────────────────────────────────────
    date      = datetime.now(timezone.utc).astimezone(ZoneInfo("America/Santiago"))
    year, month, day = date.year, date.month, date.day
    hour, min_, sec  = date.hour, date.minute, date.second

    prefix    = f"year={year}/month={month}/day={day}/hour={hour}/mcp={mcp_name}/tool={tool}"
    date_dict = {"year": year, "month": month, "day": day,
                 "hour": hour, "min": min_, "sec": sec}
    user      = current_user.get()

    # ── Objeto mutable que la tool usa para devolver su resultado ──────────
    class _Ctx:
        result = None

    ctx        = _Ctx()
    start_time = time.perf_counter()

    try:
        yield ctx                                          # ← el cuerpo del `async with`

        latency = round(time.perf_counter() - start_time, 4)
        save_json_to_gcs(
            {
                "mcp":     mcp_name,
                "tool":    tool,
                "user":    user,
                "latency": latency,
                "date":    date_dict,
                "input":   inputs,
                "output":  ctx.result,
                "error":   "None",
            },
            prefix,
        )

    except Exception as e:
        latency = round(time.perf_counter() - start_time, 4)
        save_json_to_gcs(
            {
                "mcp":     mcp_name,
                "tool":    tool,
                "user":    user,
                "latency": latency,
                "date":    date_dict,
                "input":   inputs,
                "output":  "None",
                "error":   str(e),
            },
            prefix,
        )
        raise                                              # re-lanza para que FastMCP lo maneje