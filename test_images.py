import requests

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Referer': 'https://www.serebii.net/quest/powerstones.shtml'
}

url = 'https://www.serebii.net/quest/stones/broadburststone.png'
r = requests.get(url, headers=headers)
print(f'Status: {r.status_code}')
print(f'Content-Type: {r.headers.get("content-type")}')
print(f'Size: {len(r.content)} bytes')
if r.status_code == 200:
    print('Image downloaded successfully')
else:
    print('Failed to download image')
