from PIL import Image


def make_gradient(w, h, color1, color2):
    img = Image.new("RGBA", (w, h))
    for y in range(h):
        ratio = y / h
        r = int(color1[0] * (1 - ratio) + color2[0] * ratio)
        g = int(color1[1] * (1 - ratio) + color2[1] * ratio)
        b = int(color1[2] * (1 - ratio) + color2[2] * ratio)
        for x in range(w):
            img.putpixel((x, y), (r, g, b, 255))
    return img


# Round bg: 512x512 degradado azul marino + violeta
round_bg = make_gradient(512, 512, (30, 60, 120), (80, 30, 100))
round_bg.save("assets/backgrounds/round_bg.png")

# Podium bg: 800x500 degradado oscuro
podium_bg = make_gradient(800, 600, (20, 20, 40), (10, 10, 20))
podium_bg.save("assets/backgrounds/podium_bg.png")
