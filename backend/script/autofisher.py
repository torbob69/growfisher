from utils import get_mouse_pos, get_image, click, press
import time, random

class Autofisher():
    def __init__(self):
        print("Point at bait position and press X when done.")
        self.bait_pos = get_mouse_pos()
        print(f"bait position initialized at{self.bait_pos}")
        
        print("Point at water position and press X when done.")
        self.water_pos = get_mouse_pos()
        print(f"water position initialized at{self.water_pos}")
        
        print("Point at deto position and press X when done.")
        self.deto_pos = get_mouse_pos()
        print(f"deto position initialized at{self.deto_pos}")
        
        print("Point at first_fish position and press X when done.")
        self.first_fish_pos = get_mouse_pos()
        print(f"first_fish position initialized at{self.first_fish_pos}")
        
        print("Point at recycle button position and press X when done.")
        self.recycle_pos = get_mouse_pos()
        print(f"recycle position initialized at{self.recycle_pos}")

        
        self.water_img = get_image("water")
        self.splash_img = get_image("splash")
        self.emptier_img = get_image("emptier")
        self.empty_fish_img = get_image("empty_fish")
        
    
    def random_delay(self):
        delay_int = random.randint(10, 35)
        delay_float = float(delay_int/100)
        return delay_float
    
    def check_water_area(self):
        pass
    
    def loop(self):
        click(*self.bait_pos)
        time.sleep(self.random_delay())
        click(*self.water_pos)
        
        # check for stoppers
        

autofisher = Autofisher()