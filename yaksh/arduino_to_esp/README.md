# Build .ino programs in esp-idf and Emulate it with QEMU
Yes, the title is pretty self-explanatory, so you need some prerequisites
- First you need to setup [esp_idf](https://rishikrishna.com/projects/esp32-emulation-qemu/#esp-idf)
- Then setup QEMU, install instructions can be found [here](https://rishikrishna.com/projects/esp32-emulation-qemu/#qemu)
- Then, setup esp_idf QEMU, not the normal QEMU, like ESP have their own custom one as espressif's repo, uk for the Xtensia boards
- Yeah that is pretty much it
## Running this
```bash
git clone https://github.com/Rishi-k-s/emulate_esp32_with_ino arduino_to_esp && cd arduino_to_esp \
chmod +x ./ino_to_running.sh 
```

then, just take any .ino file u have and do this and with some majik :stars: it should be working  
```bash
./ino_to_running.sh testing.ino # an example btw
```
Exit it by `Ctrl A , then X`

The output is saved into `output.txt`