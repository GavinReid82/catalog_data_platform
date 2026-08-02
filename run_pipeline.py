import logging
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

DBT = str(Path(sys.executable).parent / "dbt")

from dotenv import load_dotenv

from extractor.base import SupplierConfig
from extractor.vta import VtaExtractor

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
logger = logging.getLogger(__name__)

BUCKET = os.environ["S3_BUCKET"]
TODAY = date.today().isoformat()

SUPPLIERS = [
    SupplierConfig(
        name="vta",
        base_url=os.environ["VTA_BASE_URL"],
        endpoints={
            "product":     os.environ["VTA_URL_SUFFIX_PRODUCT"],
            "price":       os.environ["VTA_URL_SUFFIX_PRICE"],
            "stock":       os.environ["VTA_URL_SUFFIX_STOCK"],
            "print":       os.environ["VTA_URL_SUFFIX_PRINT"],
            "print_price": os.environ["VTA_URL_SUFFIX_PRINT_PRICE"],
        },
    ),
]

EXTRACTOR_REGISTRY = {
    "vta": VtaExtractor,
}

# KES is optional: only active when KES_BASE_URL is configured
if os.environ.get("KES_BASE_URL"):
    from extractor.kes import KesExtractor
    _kes_base = os.environ["KES_BASE_URL"]
    SUPPLIERS.append(
        SupplierConfig(
            name="kes",
            endpoints={
                "product":            f"{_kes_base}/{os.environ['KES_URL_SUFFIX_PRODUCT']}",
                "product_price":      f"{_kes_base}/{os.environ['KES_URL_SUFFIX_PRODUCT_PRICE']}",
                "print_option":       f"{_kes_base}/{os.environ['KES_URL_SUFFIX_PRINT_OPTION']}",
                "print_option_price": f"{_kes_base}/{os.environ['KES_URL_SUFFIX_PRINT_OPTION_PRICE']}",
                "stock":              f"{_kes_base}/{os.environ['KES_URL_SUFFIX_STOCK']}",
            },
        )
    )
    EXTRACTOR_REGISTRY["kes"] = KesExtractor


def extract():
    logger.info("=== EXTRACT ===")
    for config in SUPPLIERS:
        EXTRACTOR_REGISTRY[config.name](config, BUCKET).run(TODAY)
    logger.info("Extract complete.")


def transform():
    logger.info("=== TRANSFORM ===")
    for cmd in ["seed", "run", "test"]:
        subprocess.run(
            [DBT, cmd, "--project-dir", "dbt_project", "--profiles-dir", "dbt_project"],
            check=True,
        )
        logger.info(f"dbt {cmd} complete.")


if __name__ == "__main__":
    extract()
    transform()
