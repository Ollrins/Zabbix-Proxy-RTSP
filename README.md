# 🎥 Zabbix Proxy с мониторингом RTSP-потоков

Готовый Docker-образ **Zabbix Proxy** со встроенной проверкой RTSP-видеопотоков. Подходит для мониторинга IP-камер через Zabbix.

---

## ✨ Возможности

- Проверка RTSP-потока через **OpenCV** или **GStreamer**
- Резервный анализ через **FFprobe** (TCP-транспорт)
- Метрики: FPS, яркость, движение, размер кадра, разрешение, задержка
- **Числовой статус** (0/1/2) для триггеров и SLA-отчётов
- **Внутренние таймауты** — скрипт не виснет на неработающих потоках
- **Маскировка пароля** в логах и JSON
- **Подавление шума** ffmpeg/GStreamer — в Zabbix идёт только чистый JSON
- **`null` отсутствует** — все числовые поля всегда число (`0` при отсутствии данных)
- **Два лога** с автоочисткой при превышении 15 МБ
- Готовый шаблон Zabbix **`RTSP_Camera_Check`** с элементами, триггерами и графиками

---

## 🐳 Установка

### 📦 1. Скачать образ

```bash
docker pull ollrins/zabbix-proxy-rtsp:masked
```

### 📝 2. Пример простого `compose.yml`

> ⚠️ Необходимо создать сеть (если её нет)

```yaml
services:
    mysql:
        image: mariadb:11.4
        container_name: mysql
        restart: unless-stopped
        networks:
            - zabbix-net
        environment:
            MYSQL_DATABASE: zabbix_proxy
            MYSQL_USER: zabbix
            MYSQL_PASSWORD: zabbix
            MYSQL_ROOT_PASSWORD: zabbix

    zabbix-proxy:
        image: ollrins/zabbix-proxy-rtsp:masked
        container_name: zabbix-proxy
        restart: unless-stopped
        depends_on:
            - mysql
        networks:
            - zabbix-net
        environment:
            DB_SERVER_HOST: mysql
            MYSQL_DATABASE: zabbix_proxy
            MYSQL_USER: zabbix
            MYSQL_PASSWORD: zabbix
            MYSQL_ROOT_PASSWORD: zabbix

            # Имя прокси — должно совпадать с именем в веб-интерфейсе Zabbix
            ZBX_HOSTNAME: <PROXY_NAME>

            # IP-адрес вашего Zabbix Server
            ZBX_SERVER_HOST: <ZABBIX_SERVER_IP>

networks:
  zabbix-net:
    external: true
    name: zabbix-net
```

### 🎯 Что заменить

| Плейсхолдер | Что подставить | Пример |
|---|---|---|
| `<PROXY_NAME>` | Имя прокси (совпадает с Zabbix UI) | `sauron-proxy` |
| `<ZABBIX_SERVER_IP>` | IP-адрес Zabbix Server | `172.21.242.101` |

### 🛠️ Запуск

```bash
# Создать сеть (если её нет)
docker network create zabbix-net

# Запустить
docker compose up -d

# Проверить логи
docker logs -f zabbix-proxy
```

---

## 🔗 Интеграция в Zabbix

1. Тип элемента данных: **External check**
2. Ключ:
   ```
   check_rtsp.py[{$CAMERA_LOGIN},{$CAMERA_PWD},{HOST.CONN},{$CAMERA_PORT},{$CAMERA_PATH}]
   ```
3. Тип значений: **Текст**
4. **Timeout: 40s**

> `{HOST.CONN}` подставляется из интерфейса узла сети. Убедитесь, что IP доступен из прокси-контейнера.

### 📋 Готовый шаблон

Готовый шаблон Zabbix со всеми элементами, триггерами и графиками лежит в репозитории:

**➡️ [`zbx_export_templates.yaml`](https://github.com/Ollrins/Zabbix-Proxy-RTSP/blob/main/zbx_export_templates.yaml)**

Имя шаблона — **`RTSP_Camera_Check`**. Импортируется в режиме **Create new** или **Update existing**.

---

## 📊 Мониторинг RTSP в Zabbix — Макросы, Метрики и Триггеры

### 🧩 Макросы

| Макрос              | Описание                 | По умолчанию |
|---------------------|--------------------------|--------------|
| `{$CAMERA_LOGIN}`   | Логин от камеры          | `admin`      |
| `{$CAMERA_PWD}`     | Пароль от камеры         | `admin`      |
| `{$CAMERA_PORT}`    | RTSP-порт                | `554`        |
| `{$CAMERA_PATH}`    | Путь RTSP-потока         | `live/main`  |
| `{HOST.CONN}`       | IP-адрес или DNS хоста   | (из интерфейса) |

### 📡 Метрики

| Название                 | Ключ                       | Тип       | Описание                                       |
|--------------------------|----------------------------|-----------|------------------------------------------------|
| RTSP JSON Raw            | `check_rtsp.py[...]`       | EXTERNAL  | Базовый JSON-ответ (мастер-элемент)             |
| RTSP Status Code         | `rtsp.status_code`         | DEPENDENT | Числовой статус: `1`=ok, `2`=no_frames, `0`=error |
| RTSP Status              | `rtsp.status`              | DEPENDENT | Текстовый статус: `ok`, `no_frames`, `error`    |
| RTSP Latency             | `rtsp.latency`             | DEPENDENT | Задержка открытия потока (мс)                   |
| RTSP FPS                 | `rtsp.real_fps`            | DEPENDENT | Кадров в секунду                                |
| RTSP Brightness          | `rtsp.avg_brightness`      | DEPENDENT | Средняя яркость                                 |
| RTSP Motion Level        | `rtsp.frame_change_level`  | DEPENDENT | Средняя разница между кадрами                   |
| RTSP Frame Count         | `rtsp.frames_read`         | DEPENDENT | Сколько кадров получено                         |
| RTSP Frame Size (KB)     | `rtsp.avg_frame_size_kb`   | DEPENDENT | Средний объём кадра                             |
| RTSP Resolution          | `rtsp.resolution`          | DEPENDENT | Разрешение кадра (например, `1920x1080` через REGEX) |
| RTSP Note                | `rtsp.note`                | DEPENDENT | Диагностика: причина сбоя от скрипта            |

### 🎨 Value Mapping (для `rtsp.status_code`)

| Значение | Отображение |
|---|---|
| `1` | Работает |
| `2` | Нет кадров |
| `0` | Недоступна |

### 📝 Про RTSP Note

Текстовое поле для диагностики. Пустое при нормальной работе. Заполняется при сбоях:

| Ситуация | Значение `note` |
|---|---|
| Всё работает | *(пусто)* |
| OpenCV не открыл поток | `OpenCV failed to open stream` |
| Захват не дал валидных кадров | `Connected, but no valid frames` |
| Успешный фоллбэк на ffprobe | `... \| Metadata via ffprobe` |

### 🚨 Триггеры

| Название                              | Условие                                                              | Приоритет | Статус       |
|---------------------------------------|----------------------------------------------------------------------|-----------|--------------|
| Чёрный экран                          | `last(avg_brightness) < 5`                                           | Warning   | Включён      |
| Изображение замёрзло                  | `last(frame_change_level) < 1`                                       | Average   | Отключён *   |
| Низкий FPS                            | `last(real_fps) < 5`                                                 | Average   | Отключён *   |
| Камера недоступна                     | `last(status) = "error"`                                             | Warning   | Включён      |
| Камера не выдаёт кадры                | `last(status) = "no_frames"`                                         | High      | Включён      |
| **Проблема с RTSP-потоком**           | `last(status_code) <> 1` **или** `nodata(status_code,360) = 1`       | **High**  | **Включён**  |

> \* Триггеры **«Изображение замёрзло»** и **«Низкий FPS»** по умолчанию **отключены** (`DISABLED`), так как требуют индивидуальной калибровки порогов под конкретные условия освещения и сцены камеры. Включите их вручную при необходимости.

Триггер **«Проблема с RTSP-потоком»** закрывается только при выполнении **обоих** условий восстановления:

```text
last(/RTSP_Camera_Check/rtsp.status_code) = 1
and
nodata(/RTSP_Camera_Check/rtsp.status_code,360) = 0
```

### ⏱️ Таймаут скрипта

| Параметр | Значение | Где задаётся |
|---|---|---|
| Timeout элемента `RTSP JSON Raw` | **40s** | В шаблоне (`timeout: 40s`) |
| Типовая длительность работы | 4–8 сек | — |
| Худший случай | ~35 сек | Срабатывают все три таймаута (OpenCV, GStreamer, ffprobe) |
| Интервал опроса | 3 мин | `delay: 3m` в шаблоне |


### 📈 Графики

| Название                     | Содержимое                                          |
|------------------------------|-----------------------------------------------------|
| Качество видео               | Яркость (`avg_brightness`), FPS (`real_fps`), уровень движения (`frame_change_level`) |

---

## 🗂️ Лог-файлы

Внутри контейнера создаются два лога:

| Файл | Назначение | Ротация |
|---|---|---|
| `/var/log/check_rtsp.log` | Основной лог: проверки, результаты, таймауты | ✅ 15 МБ |
| `/var/log/check_rtsp_wrapper.err` | Шум ffmpeg/GStreamer, traceback Python | ✅ 15 МБ |


Просмотр:

```bash
docker exec -it zabbix-proxy tail -50 /var/log/check_rtsp.log
docker exec -it zabbix-proxy tail -50 /var/log/check_rtsp_wrapper.err
```

---

## 🔒 Безопасность

- **Пароль маскируется** в логах и JSON — `rtsp://user:***@ip:port/path`.
- **Шум ffmpeg** не попадает в stdout — Zabbix всегда получает **чистый JSON**.
- **`null` не возвращается** — все числовые поля всегда числа (`0` при отсутствии данных).

---

## 📄 Лицензия

Этот проект основан на [zabbix_rtsp](https://github.com/RoganovDA/zabbix_rtsp) от RoganovDA, распространяемом под MIT License.

Оригинальный код: Copyright (c) 2025 RoganovDA

Модификации и дополнения: Copyright (c) 2026 Ollrins Totem312

Проект распространяется под MIT License. Полный текст лицензии — в файле [LICENSE](LICENSE).

---

## 🙌 О проекте

Сделано для надёжного мониторинга IP-камер в продакшене.

Нашли баг или есть идея? Открывайте **Issue**.
Понравилось — поставьте ⭐ репозиторию.
