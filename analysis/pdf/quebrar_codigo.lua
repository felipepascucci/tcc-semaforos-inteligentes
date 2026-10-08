-- Filtro do pandoc para o PDF do relatório de validação.
-- Trecho de código (`assim`) vira \texttt com ponto de quebra depois de / _ . : - , =
-- Sem isso, um caminho longo numa célula de tabela não quebra e invade a coluna ao lado.
local especiais = {
  ["\\"] = "\\textbackslash{}", ["{"] = "\\{", ["}"] = "\\}", ["$"] = "\\$",
  ["&"] = "\\&", ["#"] = "\\#", ["_"] = "\\_", ["%"] = "\\%",
  ["^"] = "\\textasciicircum{}", ["~"] = "\\textasciitilde{}",
}
local quebra = { ["/"] = true, ["_"] = true, ["."] = true, [":"] = true,
  ["-"] = true, [","] = true, ["="] = true }

function Code(el)
  if not FORMAT:match("latex") then
    return nil
  end
  local partes = {}
  for c in el.text:gmatch(utf8.charpattern) do
    local texto = especiais[c] or c
    if quebra[c] then
      texto = texto .. "\\allowbreak{}"
    end
    table.insert(partes, texto)
  end
  return pandoc.RawInline("latex", "\\texttt{" .. table.concat(partes) .. "}")
end
