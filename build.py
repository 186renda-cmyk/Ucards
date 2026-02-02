import os
import re
import json
import datetime
from bs4 import BeautifulSoup, Comment
import copy

# Configuration
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = os.path.join(PROJECT_ROOT, 'index.html')
BLOG_DIR = os.path.join(PROJECT_ROOT, 'blog')
BASE_URL = "https://ucards.top"

# Pages to process in root
ROOT_PAGES = ['about.html', 'privacy.html', 'terms.html']

def load_soup(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        return BeautifulSoup(f, 'html.parser')

def save_soup(soup, file_path):
    # Ensure DOCTYPE
    html = str(soup)
    if not html.lower().startswith('<!doctype html>'):
        html = '<!DOCTYPE html>\n' + html
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(html)

def clean_internal_links(soup):
    """
    Remove .html suffix from internal links (href/src).
    Exception: Favicon files (.ico, .svg, .png).
    """
    for tag in soup.find_all(attrs={'href': True}):
        href = tag['href']
        # Skip external links
        if href.startswith(('http://', 'https://', '//', 'mailto:', 'tel:', '#')):
            continue
        
        # Skip if it looks like a file extension we want to keep
        if any(href.lower().endswith(ext) for ext in ['.ico', '.svg', '.png', '.jpg', '.jpeg', '.css', '.js', '.json', '.xml']):
            continue
            
        if href.endswith('.html'):
            tag['href'] = href[:-5]
            
    return soup

def extract_assets(index_soup):
    """
    Phase 1: Smart Extraction from index.html
    """
    assets = {}
    
    # 1. Layout Components
    nav = index_soup.find('nav', id='navbar')
    if nav:
        # Clean links in nav
        clean_internal_links(nav)
        assets['nav'] = nav
    
    footer = index_soup.find('footer')
    if footer:
        # Clean links in footer
        clean_internal_links(footer)
        assets['footer'] = footer
        
    # 2. Brand Assets (Favicons)
    icons = []
    # Find all icon related tags
    for link in index_soup.find_all('link'):
        rel = link.get('rel', [])
        if isinstance(rel, list):
            rel = ' '.join(rel)
        
        if 'icon' in rel:
            # Force root relative path
            href = link.get('href', '')
            if href and not href.startswith('http') and not href.startswith('data:'):
                if not href.startswith('/'):
                    href = '/' + href
                link['href'] = href
            icons.append(link)
    assets['icons'] = icons
    
    # Extract CSS/JS resources (Tailwind, Fonts, Custom Styles)
    resources = []
    head = index_soup.head
    if head:
        for tag in head.find_all(['script', 'link', 'style']):
            # Skip icons as they are handled separately
            if tag.name == 'link' and 'icon' in ' '.join(tag.get('rel', [])):
                continue
            # Skip canonical, title, meta, etc.
            if tag.name == 'meta' or tag.name == 'title':
                continue
            if tag.name == 'link' and 'canonical' in ' '.join(tag.get('rel', [])):
                continue
            
            # Keep Tailwind, Fonts, Styles
            resources.append(tag)
    assets['resources'] = resources
    
    return assets

def reconstruct_head(soup, assets, filename, page_type='page'):
    """
    Phase 2: Head Reconstruction
    """
    # Create a new head or clear existing
    if soup.head:
        soup.head.clear()
    else:
        new_head = soup.new_tag('head')
        soup.html.insert(0, new_head)
        
    head = soup.head
    
    # Original Title (or default)
    original_title = soup.find('title')
    title_text = original_title.string if original_title else "UCards"
    
    # Group A: Basic Metadata
    head.append(soup.new_tag('meta', charset='utf-8'))
    head.append(soup.new_tag('meta', attrs={'name': 'viewport', 'content': 'width=device-width, initial-scale=1.0'}))
    title_tag = soup.new_tag('title')
    title_tag.string = title_text
    head.append(title_tag)
    head.append('\n')
    
    # Group B: SEO Core
    head.append(soup.new_tag('meta', attrs={'name': 'description', 'content': 'UCards - Crypto Virtual Cards'}))
    # head.append(soup.new_tag('meta', attrs={'name': 'keywords', 'content': 'keywords'}))
    
    # Clean URL (Canonical)
    if filename == 'index.html':
        canonical_url = BASE_URL + '/'
    else:
        canonical_url = f"{BASE_URL}/{filename.replace('.html', '')}"
        if page_type == 'blog':
            canonical_url = f"{BASE_URL}/blog/{filename.replace('.html', '')}"
            
    head.append(soup.new_tag('link', rel='canonical', href=canonical_url))
    head.append('\n')
    
    # Group C: Indexing & Geo
    head.append(soup.new_tag('meta', attrs={'name': 'robots', 'content': 'index, follow'}))
    head.append(soup.new_tag('meta', attrs={'http-equiv': 'content-language', 'content': 'zh-cn'}))
    # Hreflang
    head.append(soup.new_tag('link', href=canonical_url, hreflang='x-default', rel='alternate'))
    head.append(soup.new_tag('link', href=canonical_url, hreflang='zh', rel='alternate'))
    head.append(soup.new_tag('link', href=canonical_url, hreflang='zh-CN', rel='alternate'))
    head.append('\n')
    
    # Group D: Branding & Resources
    # Favicons
    for icon in assets['icons']:
        head.append(icon)
    # CSS/JS
    for res in assets['resources']:
        head.append(res)
    head.append('\n')
    
    # Group E: Structured Data
    schemas = []
    
    # 1. Main Entity Schema
    main_type = "WebPage"
    if page_type == 'blog':
        main_type = "BlogPosting"
        if filename == 'index.html':
            main_type = "CollectionPage"

    main_schema = {
        "@context": "https://schema.org",
        "@type": main_type,
        "headline": title_text,
        "url": canonical_url,
        "mainEntityOfPage": {
            "@type": "WebPage",
            "@id": canonical_url
        }
    }
    schemas.append(main_schema)
    
    # 2. BreadcrumbList Schema
    if filename != 'index.html':
        breadcrumb_items = [
            {
                "@type": "ListItem",
                "position": 1,
                "name": "Home",
                "item": BASE_URL
            }
        ]
        
        current_pos = 2
        if page_type == 'blog':
            breadcrumb_items.append({
                "@type": "ListItem",
                "position": 2,
                "name": "Blog",
                "item": f"{BASE_URL}/blog"
            })
            current_pos = 3
            
        breadcrumb_items.append({
            "@type": "ListItem",
            "position": current_pos,
            "name": title_text,
            "item": canonical_url
        })
        
        breadcrumb_schema = {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": breadcrumb_items
        }
        schemas.append(breadcrumb_schema)
    
    script_tag = soup.new_tag('script', type='application/ld+json')
    script_tag.string = json.dumps(schemas, indent=2)
    head.append(script_tag)

def inject_sidebar(soup):
    """
    Inject sales cards sidebar into <aside>
    """
    aside = soup.find('aside')
    if not aside:
        return

    aside.clear()
    
    # Create Sidebar Container
    container = soup.new_tag('div', **{'class': 'sticky top-24 space-y-6'})
    
    # 1. Title
    title_div = soup.new_tag('div', **{'class': 'flex items-center gap-2 mb-2'})
    icon = soup.new_tag('i', **{'class': 'fa-solid fa-fire text-red-500'})
    h3 = soup.new_tag('h3', **{'class': 'text-sm font-bold text-slate-400 uppercase tracking-wider'})
    h3.string = "快速通道"
    title_div.append(icon)
    title_div.append(h3)
    container.append(title_div)

    # 2. Register Card (General Guide)
    reg_card = soup.new_tag('div', **{'class': 'relative group'})
    reg_html = BeautifulSoup("""
    <div class="absolute -inset-0.5 bg-gradient-to-b from-[#F59E0B] to-transparent rounded-2xl opacity-20 group-hover:opacity-100 blur transition duration-500"></div>
    <div class="relative bg-[#0A0A0A] rounded-xl p-5 border border-white/10 flex flex-col gap-4 transition-transform group-hover:-translate-y-1">
        <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-lg bg-yellow-500/20 flex items-center justify-center text-yellow-500 text-xl">
                <i class="fa-solid fa-credit-card"></i>
            </div>
            <div>
                <h4 class="text-base font-bold text-white leading-tight">申请加密 U 卡</h4>
                <p class="text-[10px] text-slate-400">ChatGPT · Midjourney · 支付宝</p>
            </div>
        </div>
        <div class="space-y-2">
            <div class="flex items-center gap-2 text-xs text-slate-300">
                <i class="fa-solid fa-check text-green-500"></i> 支持 USDT 直接充值
            </div>
            <div class="flex items-center gap-2 text-xs text-slate-300">
                <i class="fa-solid fa-check text-green-500"></i> 绑定微信/支付宝消费
            </div>
        </div>
        <a href="/#rank" class="block w-full py-2.5 bg-[#F59E0B] hover:bg-[#D97706] text-black font-bold text-center text-sm rounded-lg transition shadow-lg shadow-yellow-500/20">
            立即申请 <i class="fa-solid fa-arrow-right ml-1 text-xs"></i>
        </a>
    </div>
    """, 'html.parser')
    for child in list(reg_html.contents):
        reg_card.append(child)
    container.append(reg_card)

    # 3. USDT Top-up (Guide)
    guide = soup.new_tag('div', **{'class': 'relative group'})
    guide_html = BeautifulSoup("""
    <div class="absolute -inset-0.5 bg-gradient-to-b from-blue-600 to-transparent rounded-2xl opacity-20 group-hover:opacity-100 blur transition duration-500"></div>
    <div class="relative bg-[#0A0A0A] rounded-xl p-5 border border-white/10 flex flex-col gap-4 transition-transform group-hover:-translate-y-1">
        <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-lg bg-blue-600/20 flex items-center justify-center text-blue-400 text-xl">
                <i class="fa-solid fa-wallet"></i>
            </div>
            <div>
                <h4 class="text-base font-bold text-white leading-tight">USDT 充值教程</h4>
                <p class="text-[10px] text-slate-400">新手必看 · 安全不冻卡</p>
            </div>
        </div>
        <p class="text-xs text-slate-400 leading-relaxed">还没 U？手把手教你在交易所安全购买 USDT。</p>
        <a href="/#guide" class="block w-full py-2.5 bg-blue-600 hover:bg-blue-700 text-white font-bold text-center text-sm rounded-lg transition shadow-lg shadow-blue-600/20">
            查看教程 <i class="fa-solid fa-book-open ml-1 text-xs"></i>
        </a>
    </div>
    """, 'html.parser')
    for child in list(guide_html.contents):
        guide.append(child)
    container.append(guide)

    aside.append(container)

def create_article_card(soup, post):
    """
    Generate Article Card HTML
    """
    card = soup.new_tag('a', href=post['url'], **{'class': 'group block bg-[#0A0A0A] border border-white/10 rounded-2xl overflow-hidden hover:border-blue-500/30 transition duration-300 flex flex-col h-full'})
    
    # Content
    content_div = soup.new_tag('div', **{'class': 'p-8 flex flex-col flex-grow'})
    
    # Icon/Tag
    tag_div = soup.new_tag('div', **{'class': 'mb-4 flex items-center justify-between'})
    tag_span = soup.new_tag('span', **{'class': 'inline-block px-3 py-1 rounded-full bg-blue-500/10 text-blue-400 text-xs font-bold border border-blue-500/20'})
    tag_span.string = "Article"
    tag_div.append(tag_span)
    
    # Date
    date_span = soup.new_tag('span', **{'class': 'text-xs text-slate-500'})
    date_span.string = datetime.datetime.fromtimestamp(post['mod_time']).strftime('%Y-%m-%d')
    tag_div.append(date_span)
    
    content_div.append(tag_div)
    
    # Title
    h3 = soup.new_tag('h3', **{'class': 'text-xl font-bold text-white mb-4 group-hover:text-blue-400 transition line-clamp-2'})
    h3.string = post['title']
    content_div.append(h3)
    
    # Description (optional, if available)
    if 'description' in post and post['description']:
        p = soup.new_tag('p', **{'class': 'text-sm text-slate-400 mb-6 line-clamp-3 leading-relaxed'})
        p.string = post['description']
        content_div.append(p)
    
    # Arrow (at bottom)
    arrow = soup.new_tag('div', **{'class': 'mt-auto text-slate-500 text-sm font-bold flex items-center gap-2 group-hover:text-white transition'})
    arrow.string = "Read More"
    icon = soup.new_tag('i', **{'class': 'fa-solid fa-arrow-right opacity-0 -translate-x-2 group-hover:opacity-100 group-hover:translate-x-0 transition-all duration-300'})
    arrow.append(icon)
    content_div.append(arrow)
    
    card.append(content_div)
    return card

def inject_content(soup, assets, page_type='page', filename=''):
    """
    Phase 3: Content Injection
    """
    body = soup.body
    if not body:
        body = soup.new_tag('body')
        soup.html.append(body)
    
    # 1. Layout Synchronization (Header/Nav)
    # Remove existing nav/header
    for tag in body.find_all(['nav', 'header']):
        if tag.name == 'nav' and 'breadcrumb' in tag.get('aria-label', ''):
             tag.decompose() 
        elif tag.name == 'nav':
             tag.decompose()
        
    # Inject new Nav at the beginning
    if assets['nav']:
        new_nav = copy.copy(assets['nav'])
        body.insert(0, new_nav)
        
    # Inject Visible Breadcrumb (after Nav)
    # Added mt-24 to fix spacing issue with fixed navbar
    if filename != 'index.html':
        breadcrumb_nav = soup.new_tag('nav', attrs={'aria-label': 'breadcrumb', 'class': 'max-w-7xl mx-auto px-6 py-4 mt-24 text-sm text-slate-400'})
        ol = soup.new_tag('ol', attrs={'class': 'flex items-center gap-2'})
        
        # Home
        li_home = soup.new_tag('li')
        a_home = soup.new_tag('a', href='/', attrs={'class': 'hover:text-white transition'})
        a_home.string = 'Home'
        li_home.append(a_home)
        ol.append(li_home)
        
        # Separator
        li_sep = soup.new_tag('li')
        i_sep = soup.new_tag('i', attrs={'class': 'fa-solid fa-chevron-right text-[10px] opacity-50'})
        li_sep.append(i_sep)
        ol.append(li_sep)
        
        if page_type == 'blog' and filename != 'index.html':
            # Blog
            li_blog = soup.new_tag('li')
            a_blog = soup.new_tag('a', href='/blog', attrs={'class': 'hover:text-white transition'})
            a_blog.string = 'Blog'
            li_blog.append(a_blog)
            ol.append(li_blog)
            
            # Separator
            li_sep2 = soup.new_tag('li')
            i_sep2 = soup.new_tag('i', attrs={'class': 'fa-solid fa-chevron-right text-[10px] opacity-50'})
            li_sep2.append(i_sep2)
            ol.append(li_sep2)
            
        # Current
        li_curr = soup.new_tag('li', attrs={'class': 'text-white font-medium truncate max-w-[200px]'})
        # Try to find H1 for title, or fallback to filename
        h1 = soup.find('h1')
        li_curr.string = h1.get_text(strip=True) if h1 else filename.replace('.html', '')
        ol.append(li_curr)
        
        breadcrumb_nav.append(ol)
        
        # Insert after main nav
        nav_idx = 0
        for i, child in enumerate(body.children):
            if child.name == 'nav' and child.get('id') == 'navbar':
                nav_idx = i
                break
        
        body.insert(nav_idx + 1, breadcrumb_nav)
        
    # 2. Footer
    # Remove existing footer
    for tag in body.find_all('footer'):
        tag.decompose()
        
    # Inject new Footer at the end
    if assets['footer']:
        new_footer = copy.copy(assets['footer'])
        body.append(new_footer)
        
    # 4. Smart Recommendation (Blog Post only)
    if page_type == 'blog' and filename != 'index.html':
        # Inject Sidebar
        inject_sidebar(soup)

        article = body.find('article')
        if article:
            # Check if recommendation already exists
            existing_rec = article.find('section', id='recommended-reading')
            if existing_rec:
                existing_rec.decompose()
                
            rec_section = soup.new_tag('section', id='recommended-reading', **{'class': 'py-12 border-t border-white/10 mt-12'})
            rec_container = soup.new_tag('div', **{'class': 'max-w-4xl mx-auto'})
            rec_title = soup.new_tag('h3', **{'class': 'text-2xl font-bold mb-6 text-white'})
            rec_title.string = "推荐阅读"
            rec_container.append(rec_title)
            
            # Find other blog posts
            rec_list = soup.new_tag('div', **{'class': 'grid gap-6 md:grid-cols-2'})
            
            # List files in BLOG_DIR
            count = 0
            if os.path.exists(BLOG_DIR):
                for f in os.listdir(BLOG_DIR):
                    if f.endswith('.html') and f != filename and f != 'index.html':
                        # Create link
                        link_href = f"/blog/{f.replace('.html', '')}"
                        item = soup.new_tag('a', href=link_href, **{'class': 'block p-6 bg-[#0A0A0A] border border-white/10 rounded-xl hover:border-blue-500/50 transition group'})
                        item_title = soup.new_tag('div', **{'class': 'font-bold mb-2 text-slate-200 group-hover:text-blue-400'})
                        item_title.string = f.replace('.html', '').replace('-', ' ').title() # Simple title guess
                        item.append(item_title)
                        rec_list.append(item)
                        count += 1
                        if count >= 2: break
            
            # If no other posts, show Home link
            if count == 0:
                item = soup.new_tag('a', href='/', **{'class': 'block p-6 bg-[#0A0A0A] border border-white/10 rounded-xl hover:border-blue-500/50 transition group'})
                item_title = soup.new_tag('div', **{'class': 'font-bold mb-2 text-slate-200 group-hover:text-blue-400'})
                item_title.string = "返回首页"
                item.append(item_title)
                rec_list.append(item)

            rec_container.append(rec_list)
            rec_section.append(rec_container)
            article.append(rec_section)

def get_all_posts():
    """
    Scan BLOG_DIR and return sorted posts list
    """
    posts = []
    if os.path.exists(BLOG_DIR):
        for f in os.listdir(BLOG_DIR):
            if f.endswith('.html') and f != 'index.html':
                post_path = os.path.join(BLOG_DIR, f)
                try:
                    post_soup = load_soup(post_path)
                    title = "Untitled"
                    description = ""
                    
                    if post_soup.title and post_soup.title.string:
                        title = post_soup.title.string.split('|')[0].strip()
                    elif post_soup.find('h1'):
                        title = post_soup.find('h1').get_text(strip=True)
                    
                    desc_meta = post_soup.find('meta', attrs={'name': 'description'})
                    if desc_meta:
                        description = desc_meta.get('content', '')
                        
                except:
                    title = f.replace('.html', '').replace('-', ' ').title()
                    description = ""

                mod_time = os.path.getmtime(post_path)
                
                posts.append({
                    'filename': f,
                    'title': title,
                    'description': description,
                    'mod_time': mod_time,
                    'url': f"/blog/{f.replace('.html', '')}"
                })
    
    # Sort by time desc
    posts.sort(key=lambda x: x['mod_time'], reverse=True)
    return posts

def process_blog_posts(assets):
    if not os.path.exists(BLOG_DIR):
        print(f"Blog directory not found: {BLOG_DIR}")
        return
    
    all_posts = get_all_posts()

    for filename in os.listdir(BLOG_DIR):
        if not filename.endswith('.html'):
            continue
            
        file_path = os.path.join(BLOG_DIR, filename)
        print(f"Processing Blog: {filename}...")
        
        soup = load_soup(file_path)
        clean_internal_links(soup)
        reconstruct_head(soup, assets, filename, page_type='blog')
        inject_content(soup, assets, page_type='blog', filename=filename)
        
        # Special handling for Blog Index
        if filename == 'index.html':
            container = soup.find(id='all-articles')
            if container:
                container.clear()
                for post in all_posts:
                    card = create_article_card(soup, post)
                    container.append(card)
        
        save_soup(soup, file_path)

def process_root_pages(assets):
    for filename in ROOT_PAGES:
        file_path = os.path.join(PROJECT_ROOT, filename)
        if not os.path.exists(file_path):
            continue
            
        print(f"Processing Page: {filename}...")
        soup = load_soup(file_path)
        clean_internal_links(soup)
        reconstruct_head(soup, assets, filename, page_type='page')
        inject_content(soup, assets, page_type='page', filename=filename)
        save_soup(soup, file_path)

def inject_latest_articles(soup):
    """
    Inject latest blog posts into index.html
    """
    posts = get_all_posts()
    latest_posts = posts[:3]
    
    if not latest_posts:
        return

    # Create Section HTML
    section = soup.new_tag('section', id='latest-articles', **{'class': 'py-24 relative z-10 bg-[#030303] border-t border-white/5'})
    
    bg_blob = soup.new_tag('div', **{'class': 'absolute left-0 top-1/2 -translate-y-1/2 w-[500px] h-[500px] bg-blue-900/10 rounded-full blur-[100px] pointer-events-none'})
    section.append(bg_blob)

    container = soup.new_tag('div', **{'class': 'max-w-7xl mx-auto px-6 relative z-10'})
    
    header_div = soup.new_tag('div', **{'class': 'text-center mb-16'})
    h2 = soup.new_tag('h2', **{'class': 'text-3xl md:text-4xl font-bold text-white mb-4'})
    h2.string = "最新动态"
    header_div.append(h2)
    p = soup.new_tag('p', **{'class': 'text-slate-400'})
    p.string = "Web3 支付领域的最新资讯与教程"
    header_div.append(p)
    container.append(header_div)
    
    grid = soup.new_tag('div', **{'class': 'grid grid-cols-1 md:grid-cols-3 gap-6'})
    
    for post in latest_posts:
        card = create_article_card(soup, post)
        grid.append(card)
        
    container.append(grid)
    section.append(container)
    
    existing = soup.find('section', id='latest-articles')
    if existing:
        existing.replace_with(section)
    else:
        footer = soup.find('footer')
        if footer:
            footer.insert_before(section)
        else:
            soup.body.append(section)

def process_index(assets):
    print("Processing Index: index.html...")
    soup = load_soup(INDEX_PATH)
    clean_internal_links(soup)
    
    inject_latest_articles(soup)
    
    save_soup(soup, INDEX_PATH)

def generate_sitemap():
    """
    Generate sitemap.xml for all public pages.
    """
    print("Generating sitemap.xml...")
    
    urls = []
    
    # 1. Root Pages
    priority_map = {
        'index.html': '1.0',
        'about.html': '0.8',
        'privacy.html': '0.5',
        'terms.html': '0.5'
    }
    
    for filename in os.listdir(PROJECT_ROOT):
        if filename.endswith('.html') and not filename.startswith('_'):
            file_path = os.path.join(PROJECT_ROOT, filename)
            lastmod = datetime.datetime.fromtimestamp(os.path.getmtime(file_path)).strftime('%Y-%m-%d')
            
            if filename == 'index.html':
                loc = BASE_URL + '/'
            else:
                loc = f"{BASE_URL}/{filename.replace('.html', '')}"
            
            priority = priority_map.get(filename, '0.8')
            urls.append({
                'loc': loc,
                'lastmod': lastmod,
                'priority': priority
            })
            
    # 2. Blog Posts
    if os.path.exists(BLOG_DIR):
        for filename in os.listdir(BLOG_DIR):
            if filename.endswith('.html'):
                file_path = os.path.join(BLOG_DIR, filename)
                lastmod = datetime.datetime.fromtimestamp(os.path.getmtime(file_path)).strftime('%Y-%m-%d')
                loc = f"{BASE_URL}/blog/{filename.replace('.html', '')}"
                
                urls.append({
                    'loc': loc,
                    'lastmod': lastmod,
                    'priority': '0.7'
                })
    
    sitemap_content = ['<?xml version="1.0" encoding="UTF-8"?>']
    sitemap_content.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    
    for url in urls:
        sitemap_content.append('  <url>')
        sitemap_content.append(f"    <loc>{url['loc']}</loc>")
        sitemap_content.append(f"    <lastmod>{url['lastmod']}</lastmod>")
        sitemap_content.append(f"    <priority>{url['priority']}</priority>")
        sitemap_content.append('  </url>')
        
    sitemap_content.append('</urlset>')
    
    with open(os.path.join(PROJECT_ROOT, 'sitemap.xml'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(sitemap_content))
    
    print(f"Sitemap generated with {len(urls)} URLs.")

def generate_robots_txt():
    """
    Generate robots.txt
    """
    print("Generating robots.txt...")
    
    content = [
        "User-agent: *",
        "Allow: /",
        f"Sitemap: {BASE_URL}/sitemap.xml"
    ]
    
    with open(os.path.join(PROJECT_ROOT, 'robots.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(content))
        
    print("robots.txt generated.")

def main():
    print("Starting build process...")
    
    if not os.path.exists(INDEX_PATH):
        print(f"Index file not found: {INDEX_PATH}")
        return
        
    index_soup = load_soup(INDEX_PATH)
    
    print("Phase 1: Extracting assets from index.html...")
    assets = extract_assets(index_soup)
    print(f"Extracted {len(assets['icons'])} icons and {len(assets['resources'])} resources.")
    
    process_index(assets)
    process_root_pages(assets)
    
    print("Phase 2 & 3: Processing blog posts...")
    process_blog_posts(assets)
    
    generate_sitemap()
    generate_robots_txt()
    
    print("Build complete.")

if __name__ == '__main__':
    main()