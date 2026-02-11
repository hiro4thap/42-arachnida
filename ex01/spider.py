import requests
import os
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

class ImageParser(HTMLParser):
    def __init__(self, base_url):
        super().__init__()
        self.images = []
        self.parsers = []
        self.base_url = base_url
    
    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == 'img' and 'src' in attrs_dict and self.is_target(attrs_dict['src']):
            img_url = urljoin(self.base_url, attrs_dict['src'])
            self.images.append(img_url)
        elif tag == 'a' and 'href' in attrs_dict:
            link_url = urljoin(self.base_url, attrs_dict['href'])
            parser = ImageParser(link_url)
            self.parsers.append(parser)
    
    def get_filename(self, url):
        path = urlparse(url).path
        filename = os.path.basename(path)
        return filename

    def is_target(self, url):
        extension = os.path.splitext(self.get_filename(url))[1]
        target = ('.jpg', '.jpeg', '.png', '.gif', '.bmp')
        return extension in target
    
    def save_images(self, dst_folder):
        for image in self.images:
            img_url = urljoin(self.base_url, image)
            try:
                response = requests.get(img_url, timeout=5)
                response.raise_for_status()
                dst_path = os.path.join(dst_folder, self.get_filename(image))
                os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                with open(dst_path, 'wb') as f:
                    f.write(response.content)
                print(f"Saved: {dst_path}")
            except Exception as e:
                print(f"Error saving {img_url}: {e}")

class ParserService:
   def __init__(self, base_url, dst_path, depth = 5):
       self.base_url = base_url
       self.dst_path = dst_path
       self.depth = depth

   def save_images(self):
        try:
            response = requests.get(self.base_url, timeout=5)
            response.raise_for_status()
            parser = ImageParser(self.base_url)
            parser.feed(response.text)
            parser.save_images(self.dst_path)
        except Exception as e:
            print(f"Error fetching {self.base_url}: {e}")

def main():
    depth = 5
    url = 'https://photohito.com/'
    os.makedirs('./data', exist_ok=True)
    service = ParserService(url, './data/', depth)
    service.save_images()
    
if __name__ == "__main__":
    main()