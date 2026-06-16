from utils import get_mouse_pos, get_image

bait_pos = None
water_pos = None
deto_pos = None
first_fish_pos = None
recycle_pos = None


water_img = None
splash_img = None
emptier_img = None
empty_fish_img = None
num_area_img = None


while True:
    print("Point at bait position and press X when done.")
    bait_pos = get_mouse_pos()
    print(f"bait position initialized at{bait_pos}")
    
    print("Point at water position and press X when done.")
    water_pos = get_mouse_pos()
    print(f"water position initialized at{water_pos}")
    
    print("Point at deto position and press X when done.")
    deto_pos = get_mouse_pos()
    print(f"deto position initialized at{deto_pos}")
    
    print("Point at first_fish position and press X when done.")
    first_fish_pos = get_mouse_pos()
    print(f"first_fish position initialized at{first_fish_pos}")
    
    print("Point at recycle button position and press X when done.")
    recycle_pos = get_mouse_pos()
    print(f"recycle position initialized at{recycle_pos}")
    
    
    water_img = get_image("water")
    splash_img = get_image("splash")
    emptier_img = get_image("emptier")
    empty_fish_img = get_image("empty_fish")
    
    
    