sqlite3 C://Users/ChangHui/.hermes/rss-archive.db "
  SELECT COUNT(*) FROM rss_articles
  WHERE date(created_at) = date('now','localtime');
"