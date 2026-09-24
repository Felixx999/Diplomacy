.PHONY: run check fast assets clean

run:            ## запустить игру на localhost:8000
	@python3 api/server.py 8000

check:          ## все проверки: движок и интерфейс
	@python3 tools/check.py

fast:           ## быстрые проверки, без долгих прогонов
	@python3 tools/check.py --fast

status:         ## где проект стоит — первая команда сессии
	@python3 tools/status.py

assets:         ## пересобрать звуки, портреты и заглушки роликов
	@python3 tools/sound.py
	@python3 tools/portraits.py
	@python3 tools/clips.py

smoke-deps:     ## поставить jsdom для проверки интерфейса
	@npm install jsdom

clean:
	@find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
	@rm -f savegame.json
