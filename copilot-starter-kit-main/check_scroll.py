import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

capture = {'x': 1920, 'y': 49, 'width': 2560, 'height': 1343}
hunt_right = 562
scale = 1.0

cb = capture
list_x = cb['x'] + cb['width'] - max(10, int(hunt_right / scale) // 2)
list_y = cb['y'] + cb['height'] // 2

print(f"capture: x={cb['x']} y={cb['y']} w={cb['width']} h={cb['height']}")
print(f"hunt_right={hunt_right}, scale={scale}")
print(f"list_x = {cb['x']} + {cb['width']} - max(10, {int(hunt_right/scale)//2}) = {list_x}")
print(f"list_y = {cb['y']} + {cb['height']}//2 = {list_y}")
print()

hunt_x2 = cb['x'] + cb['width'] - hunt_right
print(f"Hunt window правая граница: {hunt_x2}")
print(f"list_x={list_x} — " + ("INSIDE right panel OK" if list_x > hunt_x2 else "OUTSIDE hunt panel ERR"))
print()

edge_old = cb['x'] + cb['width'] - 1
print(f"Старый edge_x = {edge_old} — за правым краем экрана (1920+2560-1={edge_old}) -> КЛИК В ПУСТОТУ")
monitor2_right = cb['x'] + cb['width']
print(f"Правый край 2-го монитора: {monitor2_right}")
print(f"edge_old={edge_old} {'внутри' if edge_old < monitor2_right else 'ЗА ПРЕДЕЛАМИ'} монитора")
print()
print(f"Новый list_x={list_x} — правая панель охоты (список ресурсов) ВНУТРИ монитора OK")
print(f"Скролл: 5 notches x3 = 15 событий колёсика за раз (было 12x5=60 стрелок)")

