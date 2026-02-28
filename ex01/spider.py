import requests
import os
import argparse
from collections import deque
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
        if tag == 'img' and 'src' in attrs_dict and self.is_target(attrs_dict['src']):
            img_url = urljoin(self.base_url, attrs_dict['src'])
            self.images.append(img_url)
        elif tag == 'a' and 'href' in attrs_dict:
            link_url = urljoin(self.base_url, attrs_dict['href'])
            self.links.append(link_url)
    
    def get_filename(self, url):
        path = urlparse(url).path
        filename = os.path.basename(path)
        return filename

    def is_target(self, url):
        extension = os.path.splitext(self.get_filename(url))[1]
        target = ('.jpg', '.jpeg', '.png', '.gif', '.bmp')
        return extension in target
    
    def get_unique_filename(self, dst_folder, filename):
        dst_path = os.path.join(dst_folder, filename)
        if not os.path.exists(dst_path):
            return dst_path
        
        name, ext = os.path.splitext(filename)
        counter = 1
        while True:
            new_filename = f"{name}_{counter}{ext}"
            new_path = os.path.join(dst_folder, new_filename)
            if not os.path.exists(new_path):
                return new_path
            counter += 1
    
    def save_images(self, dst_folder):
        for image in self.images:
            img_url = urljoin(self.base_url, image)
            try:
                response = requests.get(img_url, timeout=5)
                response.raise_for_status()
                filename = self.get_filename(image)
                dst_path = self.get_unique_filename(dst_folder, filename)
                os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                with open(dst_path, 'wb') as f:
                    f.write(response.content)
                print(f"Saved: {dst_path}")
            except Exception as e:
                print(f"Error saving {img_url}: {e}")

class ParserService:
    def __init__(self, base_url, dst_path, max_depth, recursive=False):
        parsed = urlparse(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("base_url must be a valid http(s) URL")
        if not isinstance(max_depth, int) or isinstance(max_depth, bool) or max_depth < 0:
            raise ValueError("max_depth must be a non-negative integer")
        if not isinstance(dst_path, str) or not dst_path.strip():
            raise ValueError("dst_path must be a non-empty path string")
        if not os.path.isdir(dst_path):
            raise ValueError("dst_path must be an existing directory")

        self.base_url = base_url
        self.dst_path = dst_path
        self.max_depth = max_depth
        self.recursive = recursive

    def save_images(self):
        queue = deque([(self.base_url, 0)])
        visited = set([self.base_url])

        while queue:
            current_url, depth = queue.popleft()
            if depth > self.max_depth:
                continue

            try:
                response = requests.get(current_url, timeout=5)
                response.raise_for_status()
                parser = ImageParser(current_url)
                parser.feed(response.text)
                parser.save_images(self.dst_path)

                if self.recursive and depth < self.max_depth:
                    for link in parser.links:
                        parsed = urlparse(link)
                        if parsed.scheme not in ("http", "https"):
                            continue
                        if link in visited:
                            continue
                        visited.add(link)
                        queue.append((link, depth + 1))
            except Exception as e:
                print(f"Error fetching {current_url}: {e}")

def main():
    parser = argparse.ArgumentParser(description="Download images from a URL.")
    parser.add_argument("url", help="URL to fetch images from")
    parser.add_argument("-r", "--recursive", action="store_true", help="recursively download images")
    parser.add_argument("-l", "--level", type=int, help="maximum recursion depth")
    parser.add_argument("-p", "--path", default="./data/", help="download path (default: ./data/)")
    args = parser.parse_args()

    if args.level is not None and not args.recursive:
        parser.error("-l requires -r")

    max_depth = 0
    if args.recursive:
        max_depth = args.level if args.level is not None else 5

    os.makedirs(args.path, exist_ok=True)
    service = ParserService(args.url, args.path, max_depth=max_depth, recursive=args.recursive)
    service.save_images()
    
if __name__ == "__main__":
    main()