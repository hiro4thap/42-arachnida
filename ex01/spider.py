import requests
import os
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

class ImageParser(HTMLParser):
    def __init__(self, base_url):
        super().__init__()
        self.images = []
        self.links = []
        self.base_url = base_url
    
    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == 'img' and 'src' in attrs_dict:
            img_url = urljoin(self.base_url, attrs_dict['src'])
            self.images.append(img_url)
        elif tag == 'a' and 'href' in attrs_dict:
            link_url = urljoin(self.base_url, attrs_dict['href'])
            self.links.append(link_url)

def find_images(url):
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        parser = ImageParser(url)
        parser.feed(response.text)
        return parser.images
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return []

def find_links(url):
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        parser = ImageParser(url)
        parser.feed(response.text)
        return parser.links
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return []

def save_image(url, dst_path):
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
        with open(dst_path, 'wb') as f:
            f.write(response.content)
        print(f"Saved: {dst_path}")
    except Exception as e:
        print(f"Error saving {url}: {e}")

def main():
    url = 'https://www.python.org'
    images = find_images(url)
    
    os.makedirs('./data', exist_ok=True)
    for idx, img_url in enumerate(images[:5]):
        filename = f"image_{idx}.png"
        dst_path = f'./data/{filename}'
        save_image(img_url, dst_path)

if __name__ == "__main__":
    main()

