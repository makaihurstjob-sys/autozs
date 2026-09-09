from pathlib import Path
p=Path('tools/chrome-extension/home-depot-checkout.js');s=p.read_text(encoding='utf-8');s=s.replace('const status = /\\bdelivered\\b/i.test(text)', 'const status = /\\b(?:delivered (?:on|at)|successfully delivered|package (?:was |has been )delivered)\\b/i.test(text)');p.write_text(s,encoding='utf-8')
