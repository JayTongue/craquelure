from flask import Flask, render_template, abort, send_from_directory, url_for
from markupsafe import Markup
import os
import frontmatter
from slugify import slugify


app = Flask(__name__)
app.jinja_env.filters['slugify'] = slugify

articles_dir = os.path.join(os.path.dirname(__file__), 'articles')

@app.route('/')
def home():
    articles = []
    for filename in os.listdir(articles_dir):
        if filename.endswith('.html'):  # Only HTML files
            path = os.path.join(articles_dir, filename)
            post = frontmatter.load(path)
            created = str(post.get('created', '0000-00-00'))
            edited = str(post.get('edited', '0000-00-00'))
            slug = os.path.splitext(filename)[0]

            # Get tags, split into list (or keep as string if already a list)
            raw_tags = post.get('tags', '')
            if isinstance(raw_tags, str):
                tags = [tag.strip() for tag in raw_tags.split(',')]
            else:
                tags = raw_tags  # Already a list

            articles.append({
                'slug': slug,
                'title': post.get('title', slug.title()),
                'subtitle': post.get('subtitle', ''),
                'created': created,
                'edited': edited,
                'tags': tags,
                'sort_key': created
            })

    articles.sort(key=lambda x: x['sort_key'], reverse=True)
    return render_template('home.html', articles=articles, tag_filter=None)


@app.route('/tag/<tag_slug>')
def tag_page(tag_slug):
    articles = []
    for filename in os.listdir(articles_dir):
        if filename.endswith('.html'):
            path = os.path.join(articles_dir, filename)
            post = frontmatter.load(path)
            tags = post.get('tags', [])
            # Match the slugified version of the tag
            if any(slugify(t) == tag_slug for t in tags):
                created = str(post.get('created', ''))
                edited = str(post.get('edited', ''))
                slug = os.path.splitext(filename)[0]

                articles.append({
                    'slug': slug,
                    'title': post.get('title', 'Untitled'),
                    'subtitle': post.get('subtitle', ''),
                    'created': created,
                    'edited': edited,
                    'tags': tags,
                    'sort_key': created
                })

    articles.sort(key=lambda x: x['sort_key'], reverse=True)
    return render_template('home.html', articles=articles, tag_filter=tag_slug)


@app.route('/article/<name>')
def article(name):
    path = os.path.join(articles_dir, name + '.html')
    if os.path.isfile(path):
        post = frontmatter.load(path)
        html_content = post.content  # raw HTML

        raw_tags = post.get('tags', [])
        if isinstance(raw_tags, str):
            tags = [tag.strip() for tag in raw_tags.split(',')]
        else:
            tags = raw_tags

        return render_template(
            'article.html',
            title=post.get('title', name),
            subtitle=post.get('subtitle', ''),
            content=Markup(html_content),  # Safe for direct HTML rendering
            created=str(post.get('created', 'Unknown Date')),
            edited=str(post.get('edited', 'Unknown Date')),
            tags=tags  # ✅ Pass tags into the template
        )

    abort(404)


@app.route('/articles/images/<path:filename>')
def article_image(filename):
    return send_from_directory(os.path.join(articles_dir, 'images'), filename)


@app.route('/robots.txt')
def robots():
    return app.send_static_file('robots.txt')
