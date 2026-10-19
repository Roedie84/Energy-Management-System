import re, os
t = open("/homeassistant/configuration.yaml").read()
i = t.find("recorder:")
print(t[i:i+1500] if i >= 0 else "geen recorder-blok")
for r, _, fs in os.walk("/homeassistant/packages") if os.path.isdir("/homeassistant/packages") else []:
    for f in fs:
        if "recorder" in open(os.path.join(r, f), errors="ignore").read():
            print("package:", f)
