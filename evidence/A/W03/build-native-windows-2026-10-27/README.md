# W03 Build Report — Biên dịch Native Windows ESP-IDF v6.1 (Member A)

> **Trạng thái:** `LOCAL ESP-IDF v6.1 BUILD: PASS`
> **Cổng nhóm:** `W03 TEAM GATE: PENDING_REVIEW` · **Kỹ thuật:** `W03 NOT PASS (Hardware Pending)`
> **Phân định rõ:** Tài liệu này ghi nhận bằng chứng biên dịch thực tế của firmware W03 trên môi trường Windows cục bộ với toolchain native ESP-IDF v6.1 chính thức. Nó chứng minh mã nguồn C của W03 không có lỗi biên dịch; nhưng **KHÔNG** thay thế GitHub Actions CI (đang bị chặn bởi giới hạn thanh toán của tài khoản GitHub) và **KHÔNG** phải nghiệm thu phần cứng.

---

## 1. Bối cảnh và Động lực

* **Nguyên nhân thực hiện:** Sau khi phân phối mã nguồn commit `f8587ddf8cd1364baafc2a332fb3fa11c9fed97c` lên PR #9, cả hai lần chạy GitHub Actions CI (run `40532665748` và `40532676477`) đều bị hệ thống GitHub từ chối khởi chạy sau 2–3 giây do tài khoản kho mã (`minhqng`) bị khóa hạn mức thanh toán / spending limit (`Billing & plans`).
* **Mục tiêu:** Cài đặt toolchain native ESP-IDF v6.1 chính thức trên Windows, thực hiện quy trình biên dịch cô lập bên ngoài kho mã (tương tự quy trình của GitHub Actions runner), và thu thập bằng chứng kiểm chứng độc lập.

---

## 2. Thông số Môi trường Biên dịch

| Mục | Giá trị thực tế quan sát được |
|---|---|
| **Hệ điều hành host** | Microsoft Windows 11 Pro 64-bit (Build `10.0.26300`) |
| **Công cụ quản lý cài đặt** | Espressif Installation Manager CLI (EIM) `0.20.1` qua WinGet |
| **Phiên bản ESP-IDF** | **`ESP-IDF v6.1`** (Commit `fff9895c82d744c7237be8847347bdd1b07c6643`) |
| **Đường dẫn cài đặt IDF** | `C:\Espressif\v6.1\esp-idf` |
| **Trình biên dịch chéo** | `xtensa-esp-elf-gcc.exe (crosstool-NG esp-15.2.0_20251204) 15.2.0` |
| **Hệ thống build** | `cmake version 4.0.3` + `ninja 1.12.1` + `ccache 4.12.1` |
| **Môi trường Python IDF** | `Python 3.11.9` (`C:\Espressif\tools\python\v6.1\venv`) |
| **Target phần cứng** | **`esp32s3`** |
| **Mã nguồn Git Commit** | **`f8587ddf8cd1364baafc2a332fb3fa11c9fed97c`** (Trích xuất 100% bằng `git archive`) |

---

## 3. Các Lệnh Thực thi và Kết quả

Quy trình biên dịch được chạy trong thư mục scratch cách ly `C:\Users\dlbac\Downloads\coldguard-firmware-build`:

1. **Thiết lập Target:**
   ```powershell
   idf.py set-target esp32s3
   ```
   * **Mã thoát:** `0`
   * **Log:** `raw/10-set-target.log` (44.782 bytes, SHA-256 `94c8b5b0…`)
2. **Biên dịch Firmware:**
   ```powershell
   idf.py build
   ```
   * **Mã thoát:** `0`
   * **Log:** `raw/20-idf-py-build.log` (286.162 bytes, SHA-256 `1bb3e732…`)
   * **Số bước Ninja:** `1.090` bước (bao gồm tiền xử lý linker script, sinh partition table, liên kết thư viện tĩnh và tạo image nhị phân).
   * **Cảnh báo trình biên dịch C (W03):** **`0` cảnh báo**
   * **Lỗi trình biên dịch C:** **`0` lỗi**
   * **Thông điệp hoàn tất:** `Project build complete.`

---

## 4. Sử dụng Bộ nhớ và Hiện vật Nhị phân

### 4.1. Thông số Phân vùng (Partition Usage)
* **Kích thước binary ứng dụng (`coldguard_firmware.bin`):** `0x38900` bytes (**231.680 bytes**)
* **Kích thước phân vùng app nhỏ nhất:** `0x100000` bytes (**1.048.576 bytes**)
* **Dung lượng còn trống:** `0xc7700` bytes = **816.896 bytes (78% trống)**.  
  *(Lưu ý đính chính: 0xC7700 tương ứng chính xác với 816.896 bytes; số liệu 815.872 bytes trước đây là do sơ suất tính toán).*

### 4.2. Bảng Checksum Hiện vật (SHA-256)

| Tên hiện vật | Kích thước | SHA-256 |
|---|:---:|---|
| `coldguard_firmware.bin` | 231.680 bytes | `1AA56B48D9DF6B4CCEE15275A9E2F7F400893EB1E88AD777C33C780E3A5085A9` |
| `coldguard_firmware.elf` | 4.587.188 bytes | `323C7B6D5178EC00C38E3A2202A1CD365BDE35EB532D86D387B14E1E7EF66C0C` |
| `coldguard_firmware.map` | 3.852.877 bytes | `5E12DD93A856048A71953A71C1D288052654FDDCFBCA65171367EB021DE0F1AB` |
| `bootloader.bin` | 21.120 bytes | `3FC1E578CE1095263225EBFBBFFB5E9957864CD62EC4E7BFC285A4F423B53E9A` |
| `partition-table.bin` | 3.072 bytes | `7F00B6C042A89B15B0CAC534F82ED988CAF29278FF5700B0C511EB1B5BB7C820` |
| `flasher_args.json` | 951 bytes | `8324FD03EDEC68DE3E5E2EB231C6671E260D357F548D3F9EE8C9140C58D8735F` |
| `sdkconfig` | 96.935 bytes | `8065E5836FFF0328B43550148555ECD9EE679DD324C00A7D078763C5F9B049C2` |

---

## 5. So sánh với Môi trường GitHub Actions (Linux Container)

| Tiêu chí | Bản build Native Windows này | GitHub Actions Workflow (`.github`) |
|---|---|---|
| **Hệ điều hành host** | Windows 11 Pro 64-bit | Ubuntu 24.04 (`ubuntu-latest`) |
| **Môi trường thực thi** | Native Windows Win32 Toolchain | Docker container `espressif/idf:v6.1` |
| **Phiên bản ESP-IDF** | ESP-IDF v6.1 (Tag chính thức) | ESP-IDF v6.1 (Image chính thức) |
| **Phiên bản GCC** | Xtensa GCC 15.2.0 | Xtensa GCC 15.2.0 |
| **Target** | `esp32s3` | `esp32s3` |
| **Kết quả kỹ thuật** | **PASS (100% build complete)** | **BLOCKED (Hạn mức tài khoản, chưa chạy job)** |
| **Đường dẫn trong ELF** | Định dạng đường dẫn Windows (`C:\...`) | Định dạng đường dẫn Linux (`/tmp/...`) |

---

## 6. Quy trình Tái lập (Reproduction Procedure)

Bất kỳ ai trên máy trạm Windows có cài đặt ESP-IDF v6.1 đều có thể kiểm tra lại:

```powershell
# 1. Kích hoạt môi trường ESP-IDF v6.1
. C:\Espressif\tools\Microsoft.v6.1.PowerShell_profile.ps1

# 2. Tạo thư mục scratch và trích xuất đúng commit
$targetDir = "C:\Users\dlbac\Downloads\coldguard-firmware-build"
git archive --format=tar f8587ddf8cd1364baafc2a332fb3fa11c9fed97c firmware | tar -xf - -C $targetDir --strip-components=1

# 3. Biên dịch
cd $targetDir
idf.py set-target esp32s3
idf.py build

# 4. Kiểm chứng tính toàn vẹn của bundle chứng cứ
cd C:\Users\dlbac\Downloads\coldguard-repo\A-W03-power-pzem-logic
py evidence/A/W03/build-native-windows-2026-10-27/verify_build.py
```

---

## 7. Rào cản An toàn Phần cứng Còn lại (Hardware Safety Boundaries)

Bản build thành công này **chỉ chứng minh tính đúng đắn về mặt phần mềm / cú pháp / liên kết thư viện**. Nó **KHÔNG** giải quyết các vấn đề an toàn phần cứng:
* **`TD-W03-03` (Xung đột `GPIO10`):** Tuyệt đối **NGHIÊM CẤM CẤP NGUỒN TEC / TẢI** khi chân `GPIO10` (DS18B20 1-Wire vs IBT-2 L_EN) chưa có quyết định phân định chính thức từ Member D và Leader.
* **`TD-W03-01`:** Phê duyệt mức logic TTL485-V2.0 5 V (CR-A-W01-01).
* **`TD-W03-02`:** Phê duyệt an toàn đường hồi của Shunt.
* **`TD-W03-04`:** Chấp thuận cửa sổ đo 598.99 s của TEST 132B.
