import json
import os
import sys
import tempfile
import types
import unittest


GLOBAL_DB_DIR = tempfile.TemporaryDirectory()
os.environ["DB_PATH"] = os.path.join(GLOBAL_DB_DIR.name, "global.db")

try:
    import aiohttp  # noqa: F401
    from PIL import Image, ImageDraw, ImageFont  # noqa: F401
    from loguru import logger  # noqa: F401
except ModuleNotFoundError:
    sys.modules.setdefault("aiohttp", types.ModuleType("aiohttp"))
    pil_module = types.ModuleType("PIL")
    pil_module.Image = types.SimpleNamespace()
    pil_module.ImageDraw = types.SimpleNamespace()
    pil_module.ImageFont = types.SimpleNamespace()
    sys.modules.setdefault("PIL", pil_module)

    class _Logger:
        def __getattr__(self, _name):
            return lambda *_args, **_kwargs: None

    loguru_module = types.ModuleType("loguru")
    loguru_module.logger = _Logger()
    sys.modules.setdefault("loguru", loguru_module)

from db_manager import DBManager


class ItemImagePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.manager = DBManager(os.path.join(self.temp_dir.name, "items.db"))

    def tearDown(self):
        self.manager.conn.close()
        self.temp_dir.cleanup()

    def test_extract_item_image_supports_api_key_variants(self):
        detail = json.dumps({"detailParams": {"picUrl": "https://img/new.jpg"}})

        self.assertEqual("https://img/new.jpg", self.manager.extract_item_image(detail))

    def test_extract_item_image_prioritizes_item_image_over_nested_avatar(self):
        detail = {
            "seller": {"picUrl": "https://img/avatar.jpg"},
            "picInfo": {"picUrl": "https://img/item.jpg"},
        }

        self.assertEqual("https://img/item.jpg", self.manager.extract_item_image(detail))

    def test_plain_detail_updates_description_without_replacing_json(self):
        detail = json.dumps({"picInfo": {"picUrl": "https://img/original.jpg"}})
        self.manager.batch_save_item_basic_info([{
            "cookie_id": "cookie-1",
            "item_id": "item-1",
            "item_title": "测试商品",
            "item_detail": detail,
        }])

        self.assertTrue(self.manager.update_item_detail("cookie-1", "item-1", "浏览器详情文本"))
        item = self.manager.get_item_info("cookie-1", "item-1")

        self.assertEqual(detail, item["item_detail"])
        self.assertEqual("浏览器详情文本", item["item_description"])

    def test_api_image_overwrites_existing_image(self):
        old_detail = json.dumps({"pic_info": {"picUrl": "https://img/old.jpg"}})
        new_detail = json.dumps({"detailParams": {"picUrl": "https://img/new.jpg"}})
        base_item = {
            "cookie_id": "cookie-1",
            "item_id": "item-1",
            "item_title": "测试商品",
        }
        self.manager.batch_save_item_basic_info([{**base_item, "item_detail": old_detail}])
        self.manager.batch_save_item_basic_info([{**base_item, "item_detail": new_detail}])

        item = self.manager.get_item_info("cookie-1", "item-1")

        self.assertEqual("https://img/new.jpg", item["item_image"])

    def test_item_list_falls_back_to_json_image_when_column_is_empty(self):
        detail = json.dumps({"pic_info": {"picUrl": "https://img/fallback.jpg"}})
        self.manager.batch_save_item_basic_info([{
            "cookie_id": "cookie-1",
            "item_id": "item-1",
            "item_title": "测试商品",
            "item_detail": detail,
        }])
        self.manager.conn.execute("UPDATE item_info SET item_image = ''")
        self.manager.conn.commit()

        items = self.manager.get_items_by_cookie("cookie-1")

        self.assertEqual("https://img/fallback.jpg", items[0]["item_image"])

    def test_item_replies_return_image_from_item_image_column(self):
        self.manager.batch_save_item_basic_info([{
            "cookie_id": "cookie-1",
            "item_id": "item-1",
            "item_title": "测试商品",
            "item_detail": "无图片的详情",
        }])
        self.manager.conn.execute(
            "UPDATE item_info SET item_image = ?",
            ("https://img/column.jpg",),
        )
        self.manager.conn.execute(
            "INSERT INTO item_replay (item_id, cookie_id, reply_content) VALUES (?, ?, ?)",
            ("item-1", "cookie-1", "自动回复"),
        )
        self.manager.conn.commit()

        replies = self.manager.get_itemReplays_by_cookie("cookie-1")

        self.assertEqual("https://img/column.jpg", replies[0]["item_image"])

    def test_item_replies_only_join_items_from_the_same_cookie(self):
        for cookie_id, image_url in (
            ("cookie-1", "https://img/first.jpg"),
            ("cookie-2", "https://img/second.jpg"),
        ):
            self.manager.batch_save_item_basic_info([{
                "cookie_id": cookie_id,
                "item_id": "shared-item",
                "item_title": "测试商品",
                "item_image": image_url,
            }])
        self.manager.conn.execute(
            "INSERT INTO item_replay (item_id, cookie_id, reply_content) VALUES (?, ?, ?)",
            ("shared-item", "cookie-1", "自动回复"),
        )
        self.manager.conn.commit()

        replies = self.manager.get_itemReplays_by_cookie("cookie-1")

        self.assertEqual(1, len(replies))
        self.assertEqual("https://img/first.jpg", replies[0]["item_image"])


if __name__ == "__main__":
    unittest.main()
