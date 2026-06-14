import curl_cffi
url='https://www.yad2.co.il/realestate/rent/tel-aviv-area?minPrice=7000&maxPrice=11000&zoom=17&area=1&city=5000&neighborhood=1483&bBox=32.081697%2C34.772483%2C32.084951%2C34.777194'

from curl_cffi import requests

response = requests.get(
    url=url,
    impersonate="chrome",
)

print(response.json())  # JA3 hash should match real Chrome