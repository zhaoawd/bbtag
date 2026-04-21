from __future__ import annotations

import unittest
from unittest.mock import patch

from PIL import Image

from bluetag.image import layer_to_bytes, process_bicolor_image
from bluetag.screens import ScreenProfile


class LayerEncodingTests(unittest.TestCase):
    def test_row_encoding_packs_leftmost_pixel_into_msb(self) -> None:
        layer = [[1, 0, 0, 0, 0, 0, 0, 0]]

        self.assertEqual(layer_to_bytes(layer, "row"), bytes([0x80]))

    def test_row_lsb_encoding_packs_leftmost_pixel_into_lsb(self) -> None:
        layer = [[1, 0, 0, 0, 0, 0, 0, 0]]

        self.assertEqual(layer_to_bytes(layer, "row_lsb"), bytes([0x01]))

    def test_column_msb_encoding_packs_top_pixel_into_msb(self) -> None:
        layer = [[1], [0], [0], [0], [0], [0], [0], [0]]

        self.assertEqual(layer_to_bytes(layer, "column_msb"), bytes([0x80]))

    def test_process_bicolor_image_applies_red_layer_offset_without_black_residue(
        self,
    ) -> None:
        profile = ScreenProfile(
            name="test",
            aliases=("test",),
            width=4,
            height=1,
            device_prefix="EDP-",
            cache_file=".device.test",
            transport="layer",
            default_interval_ms=100,
            mirror=False,
            detect_red=True,
            red_offset_x=1,
        )
        image = Image.new("RGB", (4, 1), "white")
        image.putpixel((1, 0), (255, 0, 0))

        with patch("bluetag.image.get_screen_profile", return_value=profile):
            black_layer, red_layer, preview = process_bicolor_image(
                image,
                "test",
                rotate=0,
                mirror=False,
                swap_wh=False,
            )

        self.assertEqual(black_layer, [[1, 1, 1, 1]])
        self.assertEqual(red_layer, [[0, 0, 1, 0]])
        self.assertEqual(
            [preview.getpixel((x, 0)) for x in range(4)],
            [(255, 255, 255), (255, 255, 255), (255, 0, 0), (255, 255, 255)],
        )


if __name__ == "__main__":
    unittest.main()
