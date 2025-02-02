from pathlib import Path

import pytest

import aiopytesseract
from aiopytesseract.models import Data


@pytest.mark.asyncio
@pytest.mark.parametrize("image", ["tests/samples/file-sample_150kB.png"])
async def test_image_to_data_with_str_image(image):
    data = await aiopytesseract.image_to_data(image)
    assert isinstance(data, list)
    assert isinstance(data[0], Data)
    assert len(data) == 22


@pytest.mark.asyncio
@pytest.mark.parametrize("image", ["tests/samples/file-sample_150kB.png"])
async def test_image_to_data_with_bytes_image(image):
    data = await aiopytesseract.image_to_data(Path(image).read_bytes())
    assert isinstance(data, list)
    assert isinstance(data[0], Data)
    assert len(data) == 22


@pytest.mark.asyncio
async def test_image_to_data_with_invalid():
    with pytest.raises(RuntimeError):
        await aiopytesseract.image_to_data("tests/samples/file-sample_150kB.pdf")


@pytest.mark.asyncio
async def test_image_to_data_with_type_not_supported():
    with pytest.raises(NotImplementedError):
        await aiopytesseract.image_to_data(None)
