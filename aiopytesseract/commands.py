import asyncio
import re
from contextlib import asynccontextmanager
from functools import singledispatch
from pathlib import Path
from typing import Any, AsyncGenerator, List, Optional, Tuple

import cattr
from aiofiles import tempfile  # type: ignore

from aiopytesseract.validators import file_exists

from .base_command import execute, execute_cmd, execute_multi_output_cmd
from .constants import (
    AIOPYTESSERACT_DEFAULT_DPI,
    AIOPYTESSERACT_DEFAULT_ENCODING,
    AIOPYTESSERACT_DEFAULT_LANGUAGE,
    AIOPYTESSERACT_DEFAULT_OEM,
    AIOPYTESSERACT_DEFAULT_PSM,
    AIOPYTESSERACT_DEFAULT_TIMEOUT,
    TESSERACT_LANGUAGES,
)
from .exceptions import TesseractRuntimeError
from .file_format import FileFormat
from .models import OSD, Box, Data, Parameter
from .returncode import ReturnCode


async def languages(
    config: str = "", encoding: str = AIOPYTESSERACT_DEFAULT_ENCODING
) -> List:
    """Tesseract available languages."""
    proc = await execute_cmd(f"--list-langs {config}")
    data = await proc.stdout.read()
    languages = []
    for line in data.decode(encoding).split():
        lang = line.strip()
        if lang in TESSERACT_LANGUAGES:
            languages.append(lang)
    return languages


async def get_languages(
    config: str = "", encoding: str = AIOPYTESSERACT_DEFAULT_ENCODING
) -> List:
    """Tesseract available languages."""
    langs = await languages(config, encoding=encoding)
    return langs


async def tesseract_version(encoding: str = AIOPYTESSERACT_DEFAULT_ENCODING) -> str:
    """Tesseract version."""
    proc = await execute_cmd("--version")
    data: bytes = await proc.stdout.readuntil()
    return data.decode(encoding).split()[1]


async def get_tesseract_version(encoding: str = AIOPYTESSERACT_DEFAULT_ENCODING) -> str:
    """Tesseract version."""
    version = await tesseract_version(encoding)
    return version


async def confidence(
    image: str,
    dpi: int = AIOPYTESSERACT_DEFAULT_DPI,
    lang: str = AIOPYTESSERACT_DEFAULT_LANGUAGE,
    oem: int = AIOPYTESSERACT_DEFAULT_OEM,
    timeout: float = AIOPYTESSERACT_DEFAULT_TIMEOUT,
    encoding: str = AIOPYTESSERACT_DEFAULT_ENCODING,
) -> float:
    """Get script confidence.

    :param image: image input to tesseract. (valid values: str)
    :param dpi: image dots per inch (DPI)
    :param oem: ocr engine modes (default: 3)
    :param timeout: command timeout (default: 30)
    """
    try:
        proc = await execute_cmd(
            f"stdin stdout -l {lang} --dpi {dpi} --psm 0 --oem {oem}"
        )
        stdout, _ = await asyncio.wait_for(
            proc.communicate(Path(image).read_bytes()), timeout=timeout
        )
        confidence_value = float(
            re.search(  # type: ignore
                r"(Script.confidence:.(\d{1,10}.\d{1,10})$)",
                stdout.decode(encoding),
            ).group(2)
        )
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError("Tesseract process timeout")
    except AttributeError:
        confidence_value = 0.0
    return confidence_value


async def deskew(
    image: str,
    dpi: int = AIOPYTESSERACT_DEFAULT_DPI,
    lang: str = AIOPYTESSERACT_DEFAULT_LANGUAGE,
    oem: int = AIOPYTESSERACT_DEFAULT_OEM,
    timeout: float = AIOPYTESSERACT_DEFAULT_TIMEOUT,
    encoding: str = AIOPYTESSERACT_DEFAULT_ENCODING,
) -> float:
    """Get Deskew angle.

    :param image: image input to tesseract. (valid values: str)
    :param dpi: image dots per inch (DPI)
    :param oem: ocr engine modes (default: 3)
    :param lang: tesseract language. (Format: eng, eng+por, eng+por+fra)
    :param timeout: command timeout (default: 30)
    """
    try:
        proc = await execute_cmd(
            f"{image} stdout -l {lang} --dpi {dpi} --psm 2 --oem {oem}"
        )
        data = await asyncio.wait_for(proc.stderr.read(), timeout=timeout)
        deskew_value = float(
            re.search(  # type: ignore
                r"(Deskew.angle:.)(\d{1,10}.\d{1,10}$)",
                data.decode(encoding),
            ).group(2)
        )
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError("Tesseract process timeout")
    except AttributeError:
        deskew_value = 0.0
    return deskew_value


async def tesseract_parameters(
    encoding: str = AIOPYTESSERACT_DEFAULT_ENCODING,
) -> List[Parameter]:
    """List of all Tesseract parameters with default value and short description.

    reference: https://tesseract-ocr.github.io/tessdoc/tess3/ControlParams.html
    """
    proc = await execute_cmd("--print-parameters")
    raw_data: bytes = await proc.stdout.read()
    data = raw_data.decode(encoding)
    params = []
    for line in data.split("\n"):
        param = re.search(r"(\w+)\s+(-?\d+.?\d{0,})\s+(.*)[^\n]$", line)
        if param:
            params.append(
                cattr.structure_attrs_fromtuple(
                    [param.group(1), param.group(2), param.group(3)], Parameter  # type: ignore
                )
            )
    return params


@singledispatch
async def image_to_string(
    image: Any,
    user_words: Optional[str] = None,
    user_patterns: Optional[str] = None,
    tessdata_dir: Optional[str] = None,
    dpi: int = AIOPYTESSERACT_DEFAULT_DPI,
    lang: str = AIOPYTESSERACT_DEFAULT_LANGUAGE,
    psm: int = AIOPYTESSERACT_DEFAULT_PSM,
    oem: int = AIOPYTESSERACT_DEFAULT_OEM,
    timeout: float = AIOPYTESSERACT_DEFAULT_TIMEOUT,
) -> str:
    """Extract string from an image.

    :param image: image input to tesseract. (valid values: str, bytes)
    :param user_words: location of user words file
    :param user_patterns: location of user patterns file
    :param dpi: image dots per inch (DPI)
    :param lang: tesseract language. (Format: eng, eng+por, eng+por+fra)
    :param psm: page segmentation modes (default: 3)
    :param oem: ocr engine modes (default: 3)
    :param timeout: command timeout (default: 30)
    """
    raise NotImplementedError(f"Type {type(image)} not supported.")


@image_to_string.register(str)
async def _(
    image: str,
    dpi: int = AIOPYTESSERACT_DEFAULT_DPI,
    lang: str = AIOPYTESSERACT_DEFAULT_LANGUAGE,
    psm: int = AIOPYTESSERACT_DEFAULT_PSM,
    oem: int = AIOPYTESSERACT_DEFAULT_OEM,
    timeout: float = AIOPYTESSERACT_DEFAULT_TIMEOUT,
    user_words: Optional[str] = None,
    user_patterns: Optional[str] = None,
    tessdata_dir: Optional[str] = None,
    encoding: str = AIOPYTESSERACT_DEFAULT_ENCODING,
) -> str:
    image_text: bytes = await execute(
        image,
        FileFormat.TXT,
        dpi,
        lang,
        psm,
        oem,
        timeout,
        user_words,
        user_patterns,
        tessdata_dir,
    )
    return image_text.decode(encoding)


@image_to_string.register(bytes)
async def _(
    image: bytes,
    dpi: int = AIOPYTESSERACT_DEFAULT_DPI,
    lang: str = AIOPYTESSERACT_DEFAULT_LANGUAGE,
    psm: int = AIOPYTESSERACT_DEFAULT_PSM,
    oem: int = AIOPYTESSERACT_DEFAULT_OEM,
    timeout: float = AIOPYTESSERACT_DEFAULT_TIMEOUT,
    user_words: Optional[str] = None,
    user_patterns: Optional[str] = None,
    tessdata_dir: Optional[str] = None,
    encoding: str = AIOPYTESSERACT_DEFAULT_ENCODING,
) -> str:
    image_text: bytes = await execute(
        image,
        FileFormat.TXT,
        dpi,
        lang,
        psm,
        oem,
        timeout,
        user_words,
        user_patterns,
        tessdata_dir,
    )
    return image_text.decode(encoding)


@singledispatch
async def image_to_hocr(
    image: Any,
    user_words: Optional[str] = None,
    user_patterns: Optional[str] = None,
    tessdata_dir: Optional[str] = None,
    dpi: int = AIOPYTESSERACT_DEFAULT_DPI,
    lang: str = AIOPYTESSERACT_DEFAULT_LANGUAGE,
    psm: int = AIOPYTESSERACT_DEFAULT_PSM,
    oem: int = AIOPYTESSERACT_DEFAULT_OEM,
    timeout: float = AIOPYTESSERACT_DEFAULT_TIMEOUT,
) -> str:
    """HOCR

    :param image: image input to tesseract. (valid values: str, bytes)
    :param user_words: location of user words file
    :param user_patterns: location of user patterns file
    :param dpi: image dots per inch (DPI)
    :param lang: tesseract language. (Format: eng, eng+por, eng+por+fra)
    :param psm: page segmentation modes (default: 3)
    :param oem: ocr engine modes (default: 3)
    :param timeout: command timeout (default: 30)
    """
    raise NotImplementedError


@image_to_hocr.register(str)
async def _(
    image: str,
    user_words: Optional[str] = None,
    user_patterns: Optional[str] = None,
    tessdata_dir: Optional[str] = None,
    dpi: int = AIOPYTESSERACT_DEFAULT_DPI,
    lang: str = AIOPYTESSERACT_DEFAULT_LANGUAGE,
    psm: int = AIOPYTESSERACT_DEFAULT_PSM,
    oem: int = AIOPYTESSERACT_DEFAULT_OEM,
    timeout: float = AIOPYTESSERACT_DEFAULT_TIMEOUT,
    encoding: str = AIOPYTESSERACT_DEFAULT_ENCODING,
) -> str:
    output: bytes = await execute(
        image,
        FileFormat.HOCR,
        dpi,
        lang,
        psm,
        oem,
        timeout,
        user_words,
        user_patterns,
        tessdata_dir,
    )
    return output.decode(encoding)


@image_to_hocr.register(bytes)
async def _(
    image: bytes,
    dpi: int = AIOPYTESSERACT_DEFAULT_DPI,
    lang: str = AIOPYTESSERACT_DEFAULT_LANGUAGE,
    psm: int = AIOPYTESSERACT_DEFAULT_PSM,
    oem: int = AIOPYTESSERACT_DEFAULT_OEM,
    timeout: float = AIOPYTESSERACT_DEFAULT_TIMEOUT,
    user_words: Optional[str] = None,
    user_patterns: Optional[str] = None,
    tessdata_dir: Optional[str] = None,
    encoding: str = AIOPYTESSERACT_DEFAULT_ENCODING,
) -> str:
    output: bytes = await execute(
        image,
        FileFormat.HOCR,
        dpi,
        lang,
        psm,
        oem,
        timeout,
        user_words,
        user_patterns,
        tessdata_dir,
    )
    return output.decode(encoding)


@singledispatch
async def image_to_pdf(
    image: Any,
    dpi: int = AIOPYTESSERACT_DEFAULT_DPI,
    lang: str = AIOPYTESSERACT_DEFAULT_LANGUAGE,
    psm: int = AIOPYTESSERACT_DEFAULT_PSM,
    oem: int = AIOPYTESSERACT_DEFAULT_OEM,
    timeout: float = AIOPYTESSERACT_DEFAULT_TIMEOUT,
    user_words: Optional[str] = None,
    user_patterns: Optional[str] = None,
    tessdata_dir: Optional[str] = None,
) -> bytes:
    """Generate a searchable PDF from an image.

    :param image: image input to tesseract. (valid values: str, bytes)
    :param user_words: location of user words file
    :param user_patterns: location of user patterns file
    :param dpi: image dots per inch (DPI)
    :param lang: tesseract language. (Format: eng, eng+por, eng+por+fra)
    :param psm: page segmentation modes (default: 3)
    :param oem: ocr engine modes (default: 3)
    :param timeout: command timeout (default: 30)
    """
    raise NotImplementedError


@image_to_pdf.register(str)
async def _(
    image: str,
    dpi: int = AIOPYTESSERACT_DEFAULT_DPI,
    lang: str = AIOPYTESSERACT_DEFAULT_LANGUAGE,
    psm: int = AIOPYTESSERACT_DEFAULT_PSM,
    oem: int = AIOPYTESSERACT_DEFAULT_OEM,
    timeout: float = AIOPYTESSERACT_DEFAULT_TIMEOUT,
    user_words: Optional[str] = None,
    user_patterns: Optional[str] = None,
    tessdata_dir: Optional[str] = None,
) -> bytes:
    output: bytes = await execute(
        image,
        FileFormat.PDF,
        dpi,
        lang,
        psm,
        oem,
        timeout,
        user_words,
        user_patterns,
        tessdata_dir,
    )
    return output


@image_to_pdf.register(bytes)
async def _(
    image: bytes,
    dpi: int = AIOPYTESSERACT_DEFAULT_DPI,
    lang: str = AIOPYTESSERACT_DEFAULT_LANGUAGE,
    psm: int = AIOPYTESSERACT_DEFAULT_PSM,
    oem: int = AIOPYTESSERACT_DEFAULT_OEM,
    timeout: float = AIOPYTESSERACT_DEFAULT_TIMEOUT,
    user_words: Optional[str] = None,
    user_patterns: Optional[str] = None,
    tessdata_dir: Optional[str] = None,
) -> bytes:
    output: bytes = await execute(
        image,
        FileFormat.PDF,
        dpi,
        lang,
        psm,
        oem,
        timeout,
        user_words,
        user_patterns,
        tessdata_dir,
    )
    return output


@singledispatch
async def image_to_boxes(
    image: Any, timeout: float = AIOPYTESSERACT_DEFAULT_TIMEOUT
) -> List[Box]:
    """Bounding box estimates.

    :param image: image input to tesseract. (valid values: str, bytes)
    :param timeout: command timeout (default: 30)
    """
    raise NotImplementedError


@image_to_boxes.register(str)
async def _(image: str, timeout: float = AIOPYTESSERACT_DEFAULT_TIMEOUT) -> List[Box]:
    file_exists(image)
    boxes = await image_to_boxes(Path(image).read_bytes(), timeout)
    return boxes


@image_to_boxes.register(bytes)
async def _(
    image: bytes,
    timeout: float = AIOPYTESSERACT_DEFAULT_TIMEOUT,
    encoding: str = AIOPYTESSERACT_DEFAULT_ENCODING,
) -> List[Box]:
    try:
        proc = await execute_cmd("stdin stdout batch.nochop makebox")
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(image), timeout=timeout
        )
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError("Tesseract process timeout")
    if proc.returncode != ReturnCode.SUCCESS:
        raise TesseractRuntimeError(stderr.decode(encoding))
    data = stdout.decode(encoding)
    datalen = len(data.split("\n")) - 1
    boxes = []
    for line in data.split("\n")[:datalen]:
        boxes.append(cattr.structure_attrs_fromtuple(line.split(), Box))
    return boxes


@singledispatch
async def image_to_data(
    image: Any,
    dpi: int = AIOPYTESSERACT_DEFAULT_DPI,
    timeout: float = AIOPYTESSERACT_DEFAULT_TIMEOUT,
) -> List[Data]:
    """Information about boxes, confidences, line and page numbers.

    :param image: image input to tesseract. (valid values: str, bytes)
    :param dpi: image dots per inch (DPI)
    """
    raise NotImplementedError


@image_to_data.register(str)
async def _(
    image: str,
    dpi: int = AIOPYTESSERACT_DEFAULT_DPI,
    timeout: float = AIOPYTESSERACT_DEFAULT_TIMEOUT,
) -> List[Data]:
    file_exists(image)
    data_values = await image_to_data(Path(image).read_bytes(), dpi, timeout)
    return data_values


@image_to_data.register(bytes)
async def _(
    image: bytes,
    dpi: int = AIOPYTESSERACT_DEFAULT_DPI,
    timeout: float = AIOPYTESSERACT_DEFAULT_TIMEOUT,
    encoding: str = AIOPYTESSERACT_DEFAULT_ENCODING,
) -> List[Data]:
    try:
        proc = await execute_cmd(f"stdin stdout -c tessedit_create_tsv=1 --dpi {dpi}")
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(image), timeout=timeout
        )
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError("Tesseract process timeout")
    if proc.returncode != ReturnCode.SUCCESS:
        raise TesseractRuntimeError(stderr.decode(encoding))
    data: str = stdout.decode(encoding)
    datalen = len(data.split("\n")) - 1
    params = []
    for line in data.split("\n")[1:datalen]:
        param = line.split()
        params.append(cattr.structure_attrs_fromtuple(param, Data))  # type: ignore
    return params


@singledispatch
async def image_to_osd(
    image: Any,
    dpi: int = AIOPYTESSERACT_DEFAULT_DPI,
    oem: int = AIOPYTESSERACT_DEFAULT_OEM,
    timeout: float = AIOPYTESSERACT_DEFAULT_TIMEOUT,
    encoding: str = AIOPYTESSERACT_DEFAULT_ENCODING,
) -> OSD:
    """Information about orientation and script detection.

    :param image: image input to tesseract. (valid values: str, bytes)
    :param dpi: image dots per inch (DPI)
    :param oem: ocr engine modes (default: 3)
    :param timeout: command timeout (default: 30)
    """
    raise NotImplementedError


@image_to_osd.register(str)
async def _(
    image: str,
    dpi: int = AIOPYTESSERACT_DEFAULT_DPI,
    oem: int = AIOPYTESSERACT_DEFAULT_OEM,
    timeout: float = AIOPYTESSERACT_DEFAULT_TIMEOUT,
    encoding: str = AIOPYTESSERACT_DEFAULT_ENCODING,
) -> OSD:
    file_exists(image)
    osd = await image_to_osd(Path(image).read_bytes(), dpi, oem, timeout, encoding)
    return osd


@image_to_osd.register(bytes)
async def _(
    image: bytes,
    dpi: int = AIOPYTESSERACT_DEFAULT_DPI,
    oem: int = AIOPYTESSERACT_DEFAULT_OEM,
    timeout: float = AIOPYTESSERACT_DEFAULT_TIMEOUT,
    encoding: str = AIOPYTESSERACT_DEFAULT_ENCODING,
) -> OSD:
    data = await execute(image, FileFormat.OSD, dpi, None, 0, oem, timeout)
    osd = cattr.structure_attrs_fromtuple(
        re.findall(  # type: ignore
            r"\w+\s?\:\s{0,}(\d+.?\d{0,}|\w+)",
            data.decode(encoding),
        ),
        OSD,
    )
    return osd


@asynccontextmanager
async def run(
    image: bytes,
    output_filename: str,
    output_format: str,
    dpi: int = AIOPYTESSERACT_DEFAULT_DPI,
    lang: str = AIOPYTESSERACT_DEFAULT_LANGUAGE,
    psm: int = AIOPYTESSERACT_DEFAULT_PSM,
    oem: int = AIOPYTESSERACT_DEFAULT_OEM,
    timeout: float = AIOPYTESSERACT_DEFAULT_TIMEOUT,
    user_words: Optional[str] = None,
    user_patterns: Optional[str] = None,
    tessdata_dir: Optional[str] = None,
) -> AsyncGenerator[Tuple[str, ...], None]:
    """Run Tesseract-OCR with multiple analysis.

    This function allow run Tesseract with multiple output format with
    just one execution. For more info:

    - https://github.com/tesseract-ocr/tesseract/blob/main/doc/tesseract.1.asc#inout-arguments

    :param image: image input to tesseract. (valid values: str, bytes)
    :param user_words: location of user words file
    :param user_patterns: location of user patterns file
    :param dpi: image dots per inch (DPI)
    :param lang: tesseract language. (Format: eng, eng+por, eng+por+fra)
    :param psm: page segmentation modes (default: 3)
    :param oem: ocr engine modes (default: 3)
    :param timeout: command timeout (default: 30)
    """
    if not isinstance(image, bytes):
        raise NotImplementedError
    async with tempfile.TemporaryDirectory(prefix="aiopytesseract-") as tmpdir:
        resp = await execute_multi_output_cmd(
            image,
            f"{tmpdir}/{output_filename}",
            output_format,
            dpi,
            lang,
            psm,
            oem,
            timeout,
            user_words,
            user_patterns,
            tessdata_dir,
        )
        yield resp
