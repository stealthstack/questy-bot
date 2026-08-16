import requests
import os

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Referer': 'https://www.serebii.net/quest/powerstones.shtml'
}

stones = {
    "waitlessstone.png": "https://www.serebii.net/quest/stones/waitlessstone.png",
    "whackwhackstone.png": "https://www.serebii.net/quest/stones/whackwhackstone.png",
    "broadburststone.png": "https://www.serebii.net/quest/stones/broadburststone.png",
    "sharingstone.png": "https://www.serebii.net/quest/stones/sharingstone.png",
    "scattershotstone.png": "https://www.serebii.net/quest/stones/scattershotstone.png"
}

thumbnails = {
    "106.png": "https://raw.githubusercontent.com/Hidden50/pq/refs/heads/master/src/img/faces/106.png",
    "070.png": "https://raw.githubusercontent.com/Hidden50/pq/refs/heads/master/src/img/faces/070.png",
    "066.png": "https://raw.githubusercontent.com/Hidden50/pq/refs/heads/master/src/img/faces/066.png",
    "071.png": "https://raw.githubusercontent.com/Hidden50/pq/refs/heads/master/src/img/faces/071.png",
    "controller.png": "https://img.icons8.com/color/96/000000/controller.png"
}

os.makedirs('images', exist_ok=True)

for name, url in stones.items():
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        with open(f'images/{name}', 'wb') as f:
            f.write(r.content)
        print(f'Downloaded {name}')
    else:
        print(f'Failed {name}')

for name, url in thumbnails.items():
    r = requests.get(url)
    if r.status_code == 200:
        with open(f'images/{name}', 'wb') as f:
            f.write(r.content)
        print(f'Downloaded {name}')
    else:
        print(f'Failed {name}')
