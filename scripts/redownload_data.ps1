# ============================================
# 重新下载 Qlib 完整数据
# ============================================

Write-Host "====================================" -ForegroundColor Cyan
Write-Host "重新下载 Qlib 中国 A 股完整数据" -ForegroundColor Cyan
Write-Host "====================================" -ForegroundColor Cyan
Write-Host ""

# 1. 备份旧数据（如果有）
$OLD_DATA_DIR = "C:/Users/jay/qlib_data/cn_data"
if (Test-Path $OLD_DATA_DIR) {
    Write-Host "发现旧数据，移动到备份..." -ForegroundColor Yellow
    $BACKUP_DIR = "C:/Users/jay/qlib_data/cn_data_backup_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
    Move-Item -Path $OLD_DATA_DIR -Destination $BACKUP_DIR
    Write-Host "✓ 旧数据已备份到：$BACKUP_DIR" -ForegroundColor Green
}

# 2. 进入 Qlib 源码目录
$QLIB_SCRIPTS_DIR = "C:\Users\jay\qlib_data\qlib\scripts"
if (-not (Test-Path $QLIB_SCRIPTS_DIR)) {
    Write-Host "错误：Qlib 源码目录不存在：$QLIB_SCRIPTS_DIR" -ForegroundColor Red
    Write-Host "请先克隆 Qlib 仓库:" -ForegroundColor Yellow
    Write-Host "  git clone https://github.com/microsoft/qlib.git C:\Users\jay\qlib_data\qlib" -ForegroundColor White
    exit 1
}

Write-Host "Qlib 脚本目录：$QLIB_SCRIPTS_DIR" -ForegroundColor Gray
Write-Host ""

# 3. 下载数据
Write-Host "开始下载数据..." -ForegroundColor Yellow
Write-Host "这将下载约 1-2GB 的数据，可能需要 10-30 分钟" -ForegroundColor Gray
Write-Host ""

# 使用 Python 执行下载
conda run -n qlib_rdagent python -c "
from qlib.tests.data import GetData
import os

print('下载 Qlib 数据...')
print('目标目录：C:/Users/jay/qlib_data/cn_data')

# 下载中国 A 股数据
GetData().qlib_data(
    target_dir=r'C:/Users/jay/qlib_data/cn_data',
    region='cn',
    interval='1d',
    exists_skip=False
)

print('✓ 数据下载完成!')
"

if ($LASTEXITCODE -ne 0) {
    Write-Host "错误：下载失败" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "====================================" -ForegroundColor Cyan
Write-Host "数据下载完成！" -ForegroundColor Green
Write-Host "====================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "下一步:" -ForegroundColor Yellow
Write-Host "  python examples/check_data.py" -ForegroundColor White
Write-Host ""
