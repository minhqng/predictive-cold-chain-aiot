# W03 Build Report — Native Windows ESP-IDF v6.1 trên working tree (2026-10-28)

> **Trạng thái:** `LOCAL ESP-IDF v6.1 BUILD: PASS` trên **working tree hiện tại** của
> `A-W03-power-pzem-logic` (bao gồm thay đổi firmware chưa commit).
> **Kết luận:** `DONE` cho lớp biên dịch · phần vật lý `HARDWARE-LIMITED`
>
> Bundle này **bổ sung** cho `build-native-windows-2026-10-27/`, không thay thế nó. Bundle cũ
> chứng minh commit `f8587dd` biên dịch được; bundle này chứng minh **đúng mã nguồn sẽ được
> giao** (working tree, có pin map v2 + safe-OFF 3 chân + comment IBT-2 đã sửa) biên dịch được.
> Cả hai **KHÔNG** phải GitHub Actions CI và **KHÔNG** phải nghiệm thu phần cứng.

---

## 1. Vì sao cần bản build thứ hai

Bundle `2026-10-27` build từ `git archive f8587dd`, tức là **không** bao gồm các thay đổi
firmware còn nằm trong working tree (`cg_actuator.c`, `cg_actuator.h`, `cg_door.h`, `cg_log.c`,
`cg_log.h`, `coldguard_config.h`). Nếu chỉ dựa vào bundle cũ, bằng chứng compile sẽ không khớp
với nội dung thực sự được commit sau này. Bản 2026-10-28 copy nguyên working tree
(`cp -a firmware/. <scratch>/`) và build lại từ đầu.

## 2. Trạng thái nguồn

| Mục | Giá trị |
|---|---|
| Worktree | `C:\Users\dlbac\Downloads\coldguard-repo\A-W03-power-pzem-logic` |
| HEAD | `d54250cc4a57651d410de5588592f992afc2a034` (`docs: native build evidence`) |
| Thay đổi chưa commit được build | `firmware/main/`: `cg_actuator.c`, `cg_actuator.h`, `cg_door.h`, `cg_log.c`, `cg_log.h`, `coldguard_config.h` |
| Cách copy | `cp -a firmware/. <scratch>/` (working tree, không phải `git archive`) |
| Thư mục scratch | `C:\Users\dlbac\Downloads\coldguard-firmware-build-w03-20261028` |

## 3. Môi trường và lệnh

| Mục | Giá trị |
|---|---|
| Host | Windows 11 Pro 64-bit (build `10.0.26300`) |
| ESP-IDF | v6.1 tại `C:\Espressif\v6.1\esp-idf` |
| Profile | `C:\Espressif\tools\Microsoft.v6.1.PowerShell_profile.ps1` |
| Target | `esp32s3` |

```powershell
$env:MSYSTEM=$null
. C:\Espressif\tools\Microsoft.v6.1.PowerShell_profile.ps1
idf.py set-target esp32s3   # raw/10-set-target.log
idf.py build                # raw/20-idf-py-build.log
```

Cả hai lệnh thoát với mã `0`.

## 4. Kết quả

| Hạng mục | Giá trị thực đo từ log |
|---|---|
| Thông điệp hoàn tất | `Project build complete.` |
| Bước Ninja | `1090/1090` |
| Warning trình biên dịch | `0` |
| Error trình biên dịch | `0` |
| `coldguard_firmware.bin` | `0x38920` bytes (231.712), trống `0xc76e0` bytes (816.864, 78%) |
| `bootloader.bin` | `0x5280` bytes (21.120), trống `0x2d80` bytes (36%) |
| Phân vùng app | `0x100000` bytes (1.048.576) |

### 4.1. SHA-256 hiện vật nhị phân (từ thư mục scratch)

| Hiện vật | SHA-256 |
|---|---|
| `build/coldguard_firmware.bin` | `3855196680e675ff792eeb85f765dc1f6c8e3ee976f14a874eeafd243823fe4d` |
| `build/coldguard_firmware.elf` | `7f1e83b7c9872014c8ad14665b493b2a25aa8d8d67ec7d4461aee2c24cf9fc02` |
| `build/bootloader/bootloader.bin` | `4bceb7365982f0851bfb570f77ac8b02d3867d33970b4f90a182247eac0b0d15` |
| `build/partition_table/partition-table.bin` | `7f00b6c042a89b15b0cac534f82ed988caf29278ff5700b0c511eb1b5bb7c820` |

Các hash này nhận diện binary sinh ra từ bản copy scratch; **không** có binary nào được nạp
lên board. Kích thước tăng so với bundle 2026-10-27 (`0x38900` → `0x38920`) là do các thay đổi
working tree, không phải do môi trường toolchain.

### 4.2. Toàn vẹn bundle

`SHA256SUMS.txt` phủ ba file trong `raw/`; `py verify_build.py` kiểm hash, marker
`Project build complete.`, `[1090/1090]`, dòng kích thước app, `Set Target to: esp32s3`, và
đếm 0 warning/0 error. Chạy từ thư mục bundle:

```powershell
py verify_build.py
```

## 5. Ranh giới

- Đây là **LOCAL native build**, không phải GitHub Actions CI. CI vẫn
  `INFRASTRUCTURE-LIMITED` (hạn mức thanh toán GitHub — `Billing & plans`).
- Compile chỉ chứng minh cú pháp/liên kết của working tree được copy. Nó **không** kiểm tra
  mức logic RS-485, frame PZEM thật, hành vi cold-boot IBT-2, topology shunt hay TEC-OFF.
- **Không** cấp nguồn TEC, **không** tạo PWM, **không** flash. Các điều kiện an toàn điện trong
  `hardware-deviation-and-safety.md` giữ nguyên hiệu lực.

## 6. Tái lập

```powershell
$env:MSYSTEM=$null
. C:\Espressif\tools\Microsoft.v6.1.PowerShell_profile.ps1
$src = "C:\Users\dlbac\Downloads\coldguard-repo\A-W03-power-pzem-logic\firmware"
$dst = "C:\Users\dlbac\Downloads\coldguard-firmware-build-w03-20261028"
New-Item -ItemType Directory -Force $dst | Out-Null
Copy-Item -Recurse -Force "$src\*" $dst
cd $dst
idf.py set-target esp32s3
idf.py build

cd C:\Users\dlbac\Downloads\coldguard-repo\A-W03-power-pzem-logic\evidence\A\W03\build-native-windows-2026-10-28
py verify_build.py
```
