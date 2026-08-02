import logging
import requests
from urllib.request import urlopen
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


def get_with_retry(url: str, timeout: int = 30) -> bytes:
    session = requests.Session()
    retries = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    session.mount("https://", HTTPAdapter(max_retries=retries))
    session.mount("http://", HTTPAdapter(max_retries=retries))

    try:
        logger.info(f"Requesting: {url}")
        response = session.get(url, timeout=timeout, stream=False)
        response.raise_for_status()
        return response.content

    except requests.exceptions.ChunkedEncodingError as e:
        logger.warning(f"ChunkedEncodingError, falling back to urllib: {e}")
        try:
            with urlopen(url) as u:
                return u.read()
        except Exception as ue:
            logger.error(f"urllib fallback failed: {ue}", exc_info=True)
            raise

    except Exception as e:
        logger.error(f"Request failed for {url}: {e}", exc_info=True)
        raise
