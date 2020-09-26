import asyncio
import os
from enum import Enum
from typing import Any, Dict

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route
from pyre_extensions import none_throws

from mariner.config import FILES_DIRECTORY
from mariner.file_formats.ctb import CTBFile
from mariner.mars import ElegooMars, PrinterState


async def index(request: Request) -> FileResponse:
    return FileResponse("./frontend/dist/index.html")


async def js(request: Request) -> FileResponse:
    return FileResponse("./frontend/dist/main.js")


async def print_status(request: Request) -> JSONResponse:
    with ElegooMars() as elegoo_mars:
        selected_file = elegoo_mars.get_selected_file()
        print_status = elegoo_mars.get_print_status()

        if print_status.state == PrinterState.IDLE:
            progress = 0.0
            print_details = {}
        else:
            ctb_file = await CTBFile.read(FILES_DIRECTORY / selected_file)

            if print_status.current_byte == 0:
                current_layer = 1
            else:
                current_layer = (
                    ctb_file.end_byte_offset_by_layer.index(print_status.current_byte)
                    + 1
                )

            print_details = {
                "current_layer": current_layer,
                "layer_count": ctb_file.layer_count,
                "print_time_secs": ctb_file.print_time_secs,
            }

            progress = (
                100.0
                * none_throws(print_status.current_byte)
                / none_throws(print_status.total_bytes)
            )

        return JSONResponse(
            {
                "state": print_status.state.value,
                "selected_file": selected_file,
                "progress": progress,
                **print_details,
            }
        )


async def _prepare_file_info(filename: str) -> Dict[str, Any]:
    ctb_file = await CTBFile.read(FILES_DIRECTORY / filename)
    return {
        "filename": filename,
        "print_time_secs": ctb_file.print_time_secs,
    }


async def list_files(request: Request) -> JSONResponse:
    filename_list = os.listdir(FILES_DIRECTORY)
    files = await asyncio.gather(
        *[_prepare_file_info(filename) for filename in filename_list]
    )
    return JSONResponse(
        {
            "files": files,
        }
    )


class PrinterCommand(Enum):
    START_PRINT = "start_print"
    PAUSE_PRINT = "pause_print"
    RESUME_PRINT = "resume_print"
    CANCEL_PRINT = "cancel_print"
    REBOOT = "reboot"


def printer_command(request: Request) -> JSONResponse:
    printer_command = PrinterCommand(request.path_params["command"])
    with ElegooMars() as elegoo_mars:
        if printer_command == PrinterCommand.START_PRINT:
            # TODO: validate filename before sending it to the printer
            filename = str(request.query_params.get("filename"))
            elegoo_mars.start_printing(filename)
        elif printer_command == PrinterCommand.PAUSE_PRINT:
            elegoo_mars.pause_printing()
        elif printer_command == PrinterCommand.RESUME_PRINT:
            elegoo_mars.resume_printing()
        elif printer_command == PrinterCommand.CANCEL_PRINT:
            elegoo_mars.stop_printing()
        elif printer_command == PrinterCommand.REBOOT:
            elegoo_mars.reboot()
        return JSONResponse({"success": True})


app = Starlette(
    debug=True,
    routes=[
        Route("/", index, methods=["GET"]),
        Route("/main.js", js, methods=["GET"]),
        Route("/api/print_status", print_status, methods=["GET"]),
        Route("/api/list_files", list_files, methods=["GET"]),
        Route("/api/printer/command/{command:str}", printer_command, methods=["POST"]),
    ],
)


def main() -> None:
    uvicorn.run("mariner.server:app", host="0.0.0.0", port=5000, log_level="info")
