#!/usr/bin/env python
 
import RPi.GPIO as GPIO
import time

## 点阵的行输出控制（指定希望点亮指定行的灯）
# 在购买到的16X16的点阵LED集成板上面有4块8X8的小点阵LED屏
# 另外还有两个译码器74HC138，这两个译码器分别控制上面两个小点阵屏和下面两个小点阵屏
# 每一个译码器都有G1,G2A,G2B三个使能端口，（有些资料上也称E3,E1,E2）
# 当且仅当G2A,G2B被设置为低电平，而G1被设置为高电平时才会输出有效信号（8位中某一位为低电平），否则输出8位信号全为高电平。被设置为高电平时才会输出有效信号（8位中某一位为低电平），否则输出8位信号全为高电平。
# 点阵板上的引脚D在内部分别连接到上译码器的G2A（低电平有效）和下译码器的G1（高电平有效）
# 点阵板上的引脚G在内部分别连接到上译码器的G2B（低电平有效）和下译码器的G2A，G2B（均低电平有效）
# 上译码器的G1被直接连接到VCC上（总是高电平）
# 综上，若想上译码器输出有效，需要将引脚D和G均设置为低电平。
# 而若想下译码器输出有效，则需要将引脚D设置为高电平，引脚G设置为低电平。
D,G=32,31

# A,B,C三个端口分别连接到上下译码器74HC138的A0,A1,A2三个数据输入端口
# 译码器根据这三位高低电平的输入，输出一组8位的，有且只有一位是低电平的信号（Y0-Y7）
# 下面是输入输出的译码表：(横线符号-表示同上)
#   ===============================================================
#   Control		|	Input		|	Output	
#   E1	E2	E3	|	A2	A1	A0	|	Y7	Y6	Y5	Y4	Y3	Y2	Y1	Y0
#   ===============================================================
#   H	X	X	|	X	X	X	|	H	H	H	H	H	H	H	H
#   X	H	X	|	-	-	-	|	-	-	-	-	-	-	-	-
#   X	X	L	|	-	-	-	|	-	-	-	-	-	-	-	-
#   L	L	H	|	-	-	-	|	-	-	-	-	-	-	-	-
#   -	-	-	|	L	L	L	|	H	H	H	H	H	H	H	L
#   -	-	-	|	L	L	H	|	H	H	H	H	H	H	L	H
#   -	-	-	|	L	H	L	|	H	H	H	H	H	L	H	H
#   -	-	-	|	L	H	H	|	H	H	H	H	L	H	H	H
#   -	-	-	|	H	L	L	|	H	H	H	L	H	H	H	H
#   -	-	-	|	H	L	H	|	H	H	L	H	H	H	H	H
#   -	-	-	|	H	H	L	|	H	L	H	H	H	H	H	H
#   -	-	-	|	H	H	H	|	L	H	H	H	H	H	H	H
A,B,C=40,38,36

## 点阵的列输出控制（指定希望点亮指定列的灯）
# 板子上的DI引脚是用来串行输入位数据的，需要配合CLK引脚同时使用
# 方法是：先将LAT，CLK引脚设置为低电平，再设置DI口的位数据（0或1），然后拉高CLK电平，
# 设置的位数据在CLK的上升沿会被储存到位移缓存器中。然后再次拉低CLK引脚-设置DI位数据-拉高CLK引脚。。。
# 。。。直至16位数据全部输入完毕（8位数据满了以后由Q7'输出到第二个锁存器里继续位移？？）
# 16位数据全部输入完毕（指定哪些列点亮）以后，拉高LAT，
# 在LAT的上升沿，被储存在位移缓存器里的数据会被一次性读取出来并行输出到Q0-Q7口。
# 然后再次拉低LAT，CLK引脚-(设置DI位数据-拉高CLK引脚-位数据进入缓存器-拉低CLK引脚)16次-拉高LAT-输出16位并行数据（列数据）
DI=33
CLK=35
LAT=37

GPIO.setmode(GPIO.BOARD)
GPIO.setup(A,GPIO.OUT)
GPIO.setup(B,GPIO.OUT)
GPIO.setup(C,GPIO.OUT)
GPIO.setup(D,GPIO.OUT)

GPIO.setup(G,GPIO.OUT)
GPIO.setup(DI,GPIO.OUT)
GPIO.setup(CLK,GPIO.OUT)
GPIO.setup(LAT,GPIO.OUT)

# G端口为使能端口，低电平时输出有效1
GPIO.output(G,False)

### 常数定义 ###############################################################
# 行扫描时的时间间隔，根据硬件不同，可能需要微调至一个合适的值，
# 使得字迹看上去清晰明亮无闪烁
SLEEP_TIME = 0.001

### 常数定义 ###############################################################

### 测试二进制数据某一位是否为1
def testBit(int_type, offset):
    mask = 1 << offset
    return(int_type & mask)>0

### 根据两个字节的点阵信息输出列信号
def printRow( row, byteRight, byteLeft ):
	
	# 防止屏幕闪烁，在所有数据传输完毕以前关闭输出（使能端置高电平）
	GPIO.output(G,True)
	
	# D端口用来控制16×16点阵的上面8行输出还是下面8行输出
	# D端口设置为低电平（False）时，上面8行输出，高电平时下面8行输出
	# 所以，当指定的行数小于等于7时（0-7），将D端口置低电平
	# 指定的行数大于7时（8-15），将D端口置高电平
	GPIO.output(D, row>7)
	
	# 后面指定输出行时需要以0-7为基准计算位信息，
	# 所以当行号为8-15时，需要先调整到0-7
	if (row>7):
		row=row-8
	
	# 指定输出行
	GPIO.output(A,testBit(row,0))
	GPIO.output(B,testBit(row,1))
	GPIO.output(C,testBit(row,2))
		
	# 输入列数据
	GPIO.output(LAT,False)
	GPIO.output(CLK,False)

	# 左侧LED列数据串行输入
	# 依次从高到低取位数据（也就是从左向右取）
	for i in (7,6,5,4,3,2,1,0):
		# 设置DI位数据
		GPIO.output(DI,testBit(byteLeft, i))
		# 拉高CLK引脚
		GPIO.output(CLK,True)
		# 拉低CLK引脚
		GPIO.output(CLK,False)
	
	# 右侧LED列数据串行输入
	# 依次从高到低取位数据（也就是从左向右取）
	for i in (7,6,5,4,3,2,1,0):
		# 设置DI位数据
		GPIO.output(DI,testBit(byteRight, i))
		# 拉高CLK引脚
		GPIO.output(CLK,True)
		# 拉低CLK引脚
		GPIO.output(CLK,False)
	
	# 左右侧LED列数据共16位设置完毕，拉高LAT，
	# 将位移缓存器中的数据输出至Q1-Q8并行输出端口，即点亮当前指定行的指定列的LED灯
	GPIO.output(LAT,True) #允许HC595数据输出到Q1-Q8端口
	GPIO.output(G,False)  #HC138输出有效，打开显示
	GPIO.output(LAT,False) #锁定HC595数据输出
	
	time.sleep(0.001)
	return

### 根据输入的32个字节数组，输出到LED屏上去
def printLED( bytes32 ):   
	# 行扫描显示，指定方式是设置译码器的A0,A1,A2三个端口
	for row in range(0, 15):
		printRow(row, bytes32[row*2], bytes32[row*2 + 1])
	return

### 主程序开始
while True:
	printLED([0xEF,0xFB,0xEF,0xFB,0x00,0x80,0xEF,0xFB,0xEF,0xFB,0xBF,0xFF,0x7F,0xFF,0x00,0x80,0xEF,0xFF,0xEF,0xFF,0xEF,0xFF,0xEF,0xFF,0xEF,0xFF,0xEF,0xFF,0x0F,0xC0,0xFF,0xFF])
	
	
