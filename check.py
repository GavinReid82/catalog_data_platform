from dotenv import load_dotenv
load_dotenv()

import os
from extractor.client import get_with_retry

content = get_with_retry(os.environ["MKO_BASE_URL"] + os.environ["MKO_URL_SUFFIX_PRODUCT"])
print(content[:3000].decode())