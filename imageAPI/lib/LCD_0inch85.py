
import time
from . import lcdconfig

class LCD_0inch85(lcdconfig.RaspberryPi):

    width = 128
    height = 128 
    def command(self, cmd):
        self.digital_write(self.DC_PIN, self.GPIO.LOW)
        self.spi_writebyte([cmd])	
        
    def data(self, val):
        self.digital_write(self.DC_PIN, self.GPIO.HIGH)
        self.spi_writebyte([val])	
        
    def reset(self):
        """Reset the display"""
        self.GPIO.output(self.RST_PIN,self.GPIO.HIGH)
        time.sleep(0.01)
        self.GPIO.output(self.RST_PIN,self.GPIO.LOW)
        time.sleep(0.01)
        self.GPIO.output(self.RST_PIN,self.GPIO.HIGH)
        time.sleep(0.01)
        
    def Init(self):
        """Initialize dispaly"""  
        self.module_init()
        self.reset()

        self.command(0x36)
        self.data(0xC8)                 #self.data(0x00)

        self.command(0xB0) 		
        self.data(0xC0)  
        self.command(0xB2) 			
        self.data(0x2F)  
        self.command(0xB3) 		
        self.data(0x03) 
        self.command(0xB6) 		
        self.data(0x19)  
        self.command(0xB7) 		
        self.data(0x01)   
        
        self.command(0xAC) 
        self.data(0xCB) 
        self.command(0xAB)  
        self.data(0x0e) 
            
        self.command(0xB4) 	
        self.data(0x04) 
        
        self.command(0xA8) 
        self.data(0x19) 

        self.command(0x3A) 		
        self.data(0x05)  

        self.command(0xb8) 
        self.data(0x08) 
     
        self.command(0xE8) 
        self.data(0x24) 

        self.command(0xE9) 
        self.data(0x48) 

        self.command(0xea) 	
        self.data(0x22) 

                
        self.command(0xC6) 
        self.data(0x30) 
        self.command(0xC7) 
        self.data(0x18) 

        self.command(0xF0) 
        self.data(0x1F) 
        self.data(0x28) 
        self.data(0x04) 
        self.data(0x3E) 
        self.data(0x2A) 
        self.data(0x2E) 
        self.data(0x20) 
        self.data(0x00) 
        self.data(0x0C) 
        self.data(0x06) 
        self.data(0x00) 
        self.data(0x1C) 
        self.data(0x1F) 
        self.data(0x0f) 

        self.command(0xF1)  
        self.data(0X00) 
        self.data(0X2D) 
        self.data(0X2F) 
        self.data(0X3C) 
        self.data(0X6F) 
        self.data(0X1C) 
        self.data(0X0B) 
        self.data(0X00) 
        self.data(0X00) 
        self.data(0X00) 
        self.data(0X07) 
        self.data(0X0D) 
        self.data(0X11) 
        self.data(0X0f) 

        self.command(0x21)  

        self.command(0x11) 
        
        self.command(0x29) 
  
    def SetWindows(self, Xstart, Ystart, Xend, Yend):
        #set the X coordinates
        Xstart=Xstart+2
        Xend=Xend+2
        Ystart=Ystart+1
        Yend=Yend+1

        self.command(0x2A)
        self.data((Xstart)>>8& 0xff)               #Set the horizontal starting point to the high octet
        self.data((Xstart)   & 0xff)      #Set the horizontal starting point to the low octet
        self.data((Xend-1)>>8& 0xff)        #Set the horizontal end to the high octet
        self.data((Xend-1)   & 0xff) #Set the horizontal end to the low octet 
        
        #set the Y coordinates
        self.command(0x2B)
        self.data((Ystart)>>8& 0xff)
        self.data((Ystart)   & 0xff)
        self.data((Yend-1)>>8& 0xff)
        self.data((Yend-1)   & 0xff)

        self.command(0x2C) 
        
    def ShowImage(self,Image):
        """Set buffer to value of Python Imaging Library image."""
        """Write display buffer to physical display"""
                
        imwidth, imheight = Image.size
        if imwidth != self.width or imheight != self.height:
            raise ValueError('Image must be same dimensions as display \
                ({0}x{1}).' .format(self.width, self.height))
        img = self.np.asarray(Image)
        pix = self.np.zeros((self.height,self.width,2), dtype = self.np.uint8)
        
        pix[...,[0]] = self.np.add(self.np.bitwise_and(img[...,[0]],0xF8),self.np.right_shift(img[...,[1]],5))
        pix[...,[1]] = self.np.add(self.np.bitwise_and(self.np.left_shift(img[...,[1]],3),0xE0),self.np.right_shift(img[...,[2]],3))
        
        pix = pix.flatten().tolist()
        self.SetWindows ( 0, 0, self.width, self.height)
        self.digital_write(self.DC_PIN,self.GPIO.HIGH)
        for i in range(0,len(pix),4096):
            self.spi_writebyte(pix[i:i+4096])		
            
    def clear(self):
        """Clear contents of image buffer"""
        _buffer = [0xff]*(self.width * self.height * 2)
        self.SetWindows ( 0, 0, self.width, self.height)
        self.digital_write(self.DC_PIN,self.GPIO.HIGH)
        for i in range(0,len(_buffer),4096):
            self.spi_writebyte(_buffer[i:i+4096])	        
        

