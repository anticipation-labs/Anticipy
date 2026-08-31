import re, sys, json
def parse_symbol(libfile, name):
    txt = open(libfile).read()
    # find symbol block
    i = txt.find('(symbol "%s"' % name)
    if i < 0: return None
    # balance parens
    depth=0; j=i
    while True:
        c=txt[j]
        if c=='(':depth+=1
        elif c==')':
            depth-=1
            if depth==0: break
        j+=1
    block = txt[i:j+1]
    pins = re.findall(r'\(pin\s+(\w+)\s+\w+[\s\S]*?\(name\s+"([^"]*)"[\s\S]*?\(number\s+"([^"]*)"', block)
    fp = re.search(r'\(property\s+"Footprint"\s+"([^"]*)"', block)
    return {"pins": [(n,num,t) for (t,n,num) in pins], "footprint": fp.group(1) if fp else ""}
libs = {
 "RF_Module": ["MDBT50Q-1MV2"],
 "Battery_Management": ["BQ24075RGT"],
 "Sensor_Audio": ["SPH0641LU4H-1"],
 "Sensor_Motion": ["LIS2DH"],
 "Memory_Flash": ["W25Q128JVS"],
 "Connector": ["USB_C_Receptacle_USB2.0_16P"],
 "Power_Protection": ["USBLC6-2SC6"],
 "Regulator_Linear": ["TLV70230_SOT23-5", "AP2112K-3.3", "XC6206PxxxMR"],
 "Transistor_FET": ["2N7002"],
}
out={}
for lib, names in libs.items():
    for n in names:
        r = parse_symbol("/usr/share/kicad/symbols/%s.kicad_sym"%lib, n)
        out[lib+":"+n]=r
print(json.dumps(out, indent=1))
