# Интеграция для системы защиты от протечек Neptun ProW+Wifi
![Neptun module](https://user-images.githubusercontent.com/6770608/131808089-1a143063-1377-4b84-9ddc-fa2b91065511.png)
## Возможности
Интеграция для системы [Home Assistant](https://www.home-assistant.io/ "Home Assistant") позволяет получать:
- *сигналы от проводных датчиков*
- *сигнал о протечке*
- *данные счетчиков воды (если используются)*
- *режим уборки (вкл/выкл)*
- *состояние кранов (октрыто/закрыто)*

Для управления доступны:
- *Краны*
- *Режим уборки*
## Подключение
Просто чтоб не потерять
![Схема подключения](https://user-images.githubusercontent.com/6770608/131808117-5afb8971-9685-4976-bc93-2a297bd94901.jpg "Схема подключения")
## Описание
Интеграция мимикрирует под приложение для Android. Работает только по локальной сети без выхода в интернет. API [SST Cloud](https://api.sst-cloud.com/docs/ "SST Cloud") не используется.
#### Настройка Home Assistant
1. Скопировать папку *custom_integration*
2. Добавить *platform*

```yaml
neptun:
  host: 192.168.1.100
```
Дальше можно добавлять нужные датчики
пример:
#### Датчики протечки и другие
```yaml
binary_sensor:
  - platform: neptun
    scan_interval: 5
    monitored_variables:
      - 'sensor_3'
      - 'sensor_4'
      - 'valves'
      - 'dry'
      - 'alarm'
```
#### Счетчики воды
```yaml
sensor:
  - platform: neptun
    scan_interval: 5
    monitored_variables:
      - 'counter_1'
      - 'counter_2'
```
#### Переключатели
```yaml
switch:
  - platform: neptun
    scan_interval: 5
    name: valves

  - platform: neptun
    scan_interval: 5
    name: dry
```
Если какой-то датчик не нужен его можно просто убрать из *monitored_variables:*
## Счетчики
Можно добавить сенсоры для вывода месячных и ежедневных показаний силами Home Assistant например так:
```yaml
utility_meter:
  cold_water_daily:
    source: sensor.neptun_counter_1
    cycle: daily

  warm_water_daily:
    source: sensor.neptun_counter_2
    cycle: daily

  cold_water_monthly:
    source: sensor.neptun_counter_1
    cycle: monthly

  warm_water_monthly:
    source: sensor.neptun_counter_2
    cycle: monthly
```
