param(
    [Parameter(Mandatory = $true)][string]$Lista,
    [Parameter(Mandatory = $true)][string]$Salida,
    [string]$Dll
)

$ErrorActionPreference = 'Stop'
$utf8 = New-Object System.Text.UTF8Encoding($false)

function Esc([string]$s) {
    if ($null -eq $s) { return 'null' }
    $sb = New-Object System.Text.StringBuilder
    [void]$sb.Append('"')
    foreach ($c in $s.ToCharArray()) {
        $n = [int]$c
        if ($c -eq '"') { [void]$sb.Append('\"') }
        elseif ($c -eq '\') { [void]$sb.Append('\\') }
        elseif ($n -eq 10) { [void]$sb.Append('\n') }
        elseif ($n -eq 13) { [void]$sb.Append('\r') }
        elseif ($n -eq 9) { [void]$sb.Append('\t') }
        elseif ($n -lt 32) { [void]$sb.Append(('\u{0:x4}' -f $n)) }
        else { [void]$sb.Append($c) }
    }
    [void]$sb.Append('"')
    return $sb.ToString()
}

function Escribir([string]$json, [int]$codigo) {
    [System.IO.File]::WriteAllText($Salida, $json, $utf8)
    exit $codigo
}

function Fallo([string]$error, [string]$detalle, [int]$codigo) {
    Escribir ('{"ok":false,"error":' + (Esc $error) + ',"detalle":' + (Esc $detalle) + '}') $codigo
}

try {
    if (-not (Test-Path -LiteralPath $Lista)) {
        Fallo 'lista_inexistente' ("no existe " + $Lista) 2
    }

    $nombreDll = 'Microsoft.SqlServer.TransactSql.ScriptDom.dll'
    $candidatas = @()
    if ($Dll) {
        $candidatas += $Dll
    } elseif ($IsWindows -ne $false) {
        $candidatas += 'C:\Program Files\Microsoft SQL Server Management Studio 22\Release\Common7\IDE\Extensions\Application\' + $nombreDll
        foreach ($base in @('C:\Program Files\Microsoft Visual Studio', 'C:\Program Files (x86)\Microsoft Visual Studio')) {
            foreach ($ver in @('18', '2022')) {
                $patron = Join-Path $base ($ver + '\*\Common7\IDE\Extensions\Microsoft\SQLCommon\' + $nombreDll)
                $candidatas += @(Get-ChildItem -Path $patron -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName })
            }
        }
    }

    $usada = $null
    foreach ($c in $candidatas) {
        if (Test-Path -LiteralPath $c) {
            try { Add-Type -Path $c; $usada = $c; break } catch { }
        }
    }
    if (-not $usada) {
        if ($candidatas.Count -eq 0) {
            Fallo 'sin_dll' 'no se encontro ScriptDom: fuera de Windows no hay rutas conocidas, hay que pasar -Dll' 3
        }
        Fallo 'sin_dll' ("no se encontro ScriptDom en: " + ($candidatas -join '; ')) 3
    }

    $codigo = @'
using System;
using System.Collections.Generic;
using System.Text;
using Microsoft.SqlServer.TransactSql.ScriptDom;

public class VisitanteDinamico : TSqlFragmentVisitor
{
    public HashSet<string> VarsConcat = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
    List<object[]> pendientes = new List<object[]>();

    static bool TieneSuma(ScalarExpression e)
    {
        BinaryExpression b = e as BinaryExpression;
        if (b != null)
        {
            if (b.BinaryExpressionType == BinaryExpressionType.Add) return true;
            return TieneSuma(b.FirstExpression) || TieneSuma(b.SecondExpression);
        }
        ParenthesisExpression p = e as ParenthesisExpression;
        if (p != null) return TieneSuma(p.Expression);
        return false;
    }

    static string Texto(TSqlFragment f)
    {
        StringBuilder sb = new StringBuilder();
        for (int i = f.FirstTokenIndex; i <= f.LastTokenIndex; i++) sb.Append(f.ScriptTokenStream[i].Text);
        string s = sb.ToString().Trim();
        int nl = s.IndexOfAny(new char[] { '\r', '\n' });
        if (nl >= 0) s = s.Substring(0, nl);
        return s.Length > 200 ? s.Substring(0, 200) : s;
    }

    public override void ExplicitVisit(SetVariableStatement node)
    {
        if (node.Expression != null && (node.AssignmentKind == AssignmentKind.AddEquals || TieneSuma(node.Expression)))
            VarsConcat.Add(node.Variable.Name);
        base.ExplicitVisit(node);
    }

    public override void ExplicitVisit(DeclareVariableElement node)
    {
        if (node.Value != null && TieneSuma(node.Value)) VarsConcat.Add(node.VariableName.Value);
        base.ExplicitVisit(node);
    }

    public override void ExplicitVisit(SelectSetVariable node)
    {
        if (node.Expression != null && (node.AssignmentKind == AssignmentKind.AddEquals || TieneSuma(node.Expression)))
            VarsConcat.Add(node.Variable.Name);
        base.ExplicitVisit(node);
    }

    void Registrar(ScalarExpression e, string tipo, TSqlFragment donde)
    {
        if (e == null) return;
        if (TieneSuma(e)) { pendientes.Add(new object[] { donde.StartLine, tipo, Texto(donde), null }); return; }
        VariableReference v = e as VariableReference;
        if (v != null) pendientes.Add(new object[] { donde.StartLine, tipo, Texto(donde), v.Name });
    }

    public override void ExplicitVisit(ExecuteSpecification node)
    {
        ExecutableStringList lista = node.ExecutableEntity as ExecutableStringList;
        if (lista != null)
        {
            if (lista.Strings.Count > 1) pendientes.Add(new object[] { node.StartLine, "exec", Texto(node), null });
            else foreach (ScalarExpression s in lista.Strings) Registrar(s, "exec", node);
        }
        ExecutableProcedureReference proc = node.ExecutableEntity as ExecutableProcedureReference;
        if (proc != null && proc.ProcedureReference != null && proc.ProcedureReference.ProcedureReference != null
            && proc.ProcedureReference.ProcedureReference.Name != null
            && string.Equals(proc.ProcedureReference.ProcedureReference.Name.BaseIdentifier.Value, "sp_executesql",
                             StringComparison.OrdinalIgnoreCase)
            && proc.Parameters.Count > 0)
        {
            ExecuteParameter primero = proc.Parameters[0];
            Registrar(primero.ParameterValue, "sp_executesql", node);
        }
        base.ExplicitVisit(node);
    }

    public List<object[]> Resultado()
    {
        List<object[]> res = new List<object[]>();
        foreach (object[] p in pendientes)
        {
            if (p[3] == null || VarsConcat.Contains((string)p[3])) res.Add(new object[] { p[0], p[1], p[2] });
        }
        return res;
    }
}
'@
    Add-Type -TypeDefinition $codigo -ReferencedAssemblies $usada

    $parser = New-Object Microsoft.SqlServer.TransactSql.ScriptDom.TSql160Parser($true)
    $rutas = @([System.IO.File]::ReadAllLines($Lista, $utf8) | Where-Object { $_.Trim() -ne '' })
    $salidaArchivos = New-Object System.Collections.Generic.List[string]

    foreach ($ruta in $rutas) {
        $partes = New-Object System.Collections.Generic.List[string]
        $partes.Add('"ruta":' + (Esc $ruta))
        try {
            $bytes = [System.IO.File]::ReadAllBytes($ruta)
            $inicio = 0
            if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) { $inicio = 3 }
            $texto = $utf8.GetString($bytes, $inicio, $bytes.Length - $inicio)

            $errTokens = $null
            $tokens = $parser.GetTokenStream((New-Object System.IO.StringReader($texto)), [ref]$errTokens)
            $comentarios = New-Object System.Collections.Generic.List[string]
            foreach ($t in $tokens) {
                $tipo = $t.TokenType.ToString()
                if ($tipo -eq 'SingleLineComment' -or $tipo -eq 'MultiLineComment') {
                    $fin = $t.Line
                    if ($tipo -eq 'MultiLineComment') {
                        $fin = $t.Line + ([regex]::Matches($t.Text, "\n")).Count
                    }
                    $comentarios.Add('{"linea":' + $t.Line + ',"linea_fin":' + $fin + ',"texto":' + (Esc ($t.Text.TrimEnd("`r", "`n"))) + '}')
                }
            }

            $errParse = $null
            $arbol = $parser.Parse((New-Object System.IO.StringReader($texto)), [ref]$errParse)
            $errores = New-Object System.Collections.Generic.List[string]
            foreach ($e in $errParse) {
                $errores.Add('{"linea":' + $e.Line + ',"mensaje":' + (Esc $e.Message) + '}')
            }

            $dinamico = New-Object System.Collections.Generic.List[string]
            if ($null -ne $arbol -and $errParse.Count -eq 0) {
                $visitante = New-Object VisitanteDinamico
                $arbol.Accept($visitante)
                foreach ($d in $visitante.Resultado()) {
                    $dinamico.Add('{"linea":' + $d[0] + ',"tipo":' + (Esc $d[1]) + ',"texto":' + (Esc $d[2]) + '}')
                }
            }

            $partes.Add('"errores":[' + ($errores -join ',') + ']')
            $partes.Add('"comentarios":[' + ($comentarios -join ',') + ']')
            $partes.Add('"dinamico":[' + ($dinamico -join ',') + ']')
        } catch {
            $partes.Add('"error":' + (Esc $_.Exception.Message))
        }
        $salidaArchivos.Add('{' + ($partes -join ',') + '}')
    }

    Escribir ('{"ok":true,"dll":' + (Esc $usada) + ',"archivos":[' + ($salidaArchivos -join ',') + ']}') 0
} catch {
    Fallo 'interno' $_.Exception.Message 4
}
