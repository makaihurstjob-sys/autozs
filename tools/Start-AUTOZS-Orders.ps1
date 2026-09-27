[CmdletBinding()]
param([switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$apiBase = 'http://127.0.0.1:8000'
$dashboardBase = 'http://127.0.0.1:3000/'
try {
    $null = Invoke-RestMethod -Uri "$apiBase/health" -Method Get -TimeoutSec 10
    $page = Invoke-WebRequest -Uri $dashboardBase -UseBasicParsing -TimeoutSec 10
    $schema = Invoke-RestMethod -Uri "$apiBase/openapi.json" -Method Get -TimeoutSec 10
    $route = $schema.paths.PSObject.Properties['/supplier-orders/{supplier_order_id}/place-order']
    if (-not $route -or $page.Content -notmatch 'function placeSupplierOrder' -or $page.Content -notmatch 'launchParams.get') {
        throw 'The live dashboard has not received Place Order and Orders launcher support yet. Integrate the development checkpoint first.'
    }
    $orders = @(Invoke-RestMethod -Uri "$apiBase/orders" -Method Get -TimeoutSec 15)
    $supplierOrders = @(Invoke-RestMethod -Uri "$apiBase/supplier-orders" -Method Get -TimeoutSec 15)
    $candidates = @($orders | Where-Object {
        $orderRow = $_
        $related = @($supplierOrders | Where-Object { $_.order_id -eq $orderRow.id })
        $orderRow.account_id -ne 'sandbox' -and
        $orderRow.status -notin @('cancelled', 'shipped', 'delivered', 'refunded', 'completed') -and
        -not @($related | Where-Object { $_.external_order_id -or $_.placed_at -or $_.status -in @('queued', 'placing', 'placed', 'shipped', 'delivered', 'cancelled') }).Count
    } | Sort-Object id -Descending)
    $url = "${dashboardBase}?api=$apiBase&tab=orders"
    Write-Host 'AUTOZS Orders - review only. This launcher does not authorize or place purchases.'
    if ($candidates.Count) {
        Write-Host 'Local orders to review (live eBay eligibility is not verified):'
        $candidates | Select-Object id, ebay_order_id, status | Format-Table -AutoSize | Out-Host
        $url += '&order=' + [uri]::EscapeDataString([string]$candidates[0].id)
    } else {
        Write-Host 'No local orders needing review found. A new sale may not have synced yet.'
    }
    if ($CheckOnly) { Write-Output "Checked launch target: $url" }
    else { Start-Process -FilePath $url }
} catch {
    Write-Host "AUTOZS launcher stopped: $($_.Exception.Message)" -ForegroundColor Yellow
    exit 1
}
