# Abre o .docx do guia no Word, atualiza o sumário e os campos e salva o PDF.
#
#   powershell -ExecutionPolicy Bypass -File converter_pdf.ps1
#
# Usa uma instância do Word pela automação COM. Se o Word já estiver aberto com
# outros documentos, ele não é fechado no fim.

$ErrorActionPreference = "Stop"
$pasta = Split-Path -Parent $PSScriptRoot
$docx = Join-Path $pasta "Guia_Usuario_Semaforos_Inteligentes_v2.0.docx"
$pdf = Join-Path $pasta "Guia_Usuario_Semaforos_Inteligentes_v2.0.pdf"

$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
$abertos = $word.Documents.Count
try {
    $doc = $word.Documents.Open($docx, $false, $false, $false)
    foreach ($toc in $doc.TablesOfContents) { $toc.Update() }
    $null = $doc.Fields.Update()
    foreach ($toc in $doc.TablesOfContents) { $toc.Update() }
    $doc.Save()
    $doc.SaveAs2($pdf, 17)
    $paginas = $doc.ComputeStatistics(2)
    $doc.Close()
    Write-Output "PDF: $pdf ($paginas páginas)"
}
finally {
    if ($abertos -eq 0) { $word.Quit() }
}
