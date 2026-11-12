import contextlib
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
PLUGIN = AQUI.parent
_RUTA = AQUI / "guard_comandos.py"
sys.path.insert(0, str(AQUI))
SOBRANTES = []
NT = os.name == "nt"
PLIEGA = NT or sys.platform == "darwin"

import config_loader  # noqa: E402
from odd_ws.comun import plazo_de  # noqa: E402


def _cargar():
    spec = importlib.util.spec_from_file_location("guard_comandos", _RUTA)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


G = _cargar() if _RUTA.exists() else None


def _quitar(func, ruta, _exc):
    try:
        os.chmod(ruta, stat.S_IWRITE)
        func(ruta)
    except Exception:
        pass


def _borrar(carpeta):
    for actual, carpetas, _ in os.walk(carpeta):
        for nombre in list(carpetas):
            ruta = os.path.join(actual, nombre)
            if os.path.islink(ruta) or os.path.isjunction(ruta):
                carpetas.remove(nombre)
                (os.rmdir if NT else os.unlink)(ruta)
    shutil.rmtree(carpeta, onexc=_quitar)
    if Path(carpeta).exists():
        SOBRANTES.append(str(carpeta))


@contextlib.contextmanager
def carpeta():
    base = Path(tempfile.mkdtemp(prefix="guardc-test-"))
    try:
        yield base
    finally:
        _borrar(base)


def fw(p):
    return str(p).replace("\\", "/")


def bw(p):
    return str(p).replace("/", "\\")


def otra_grafia(p):
    p = fw(p)
    return "/" + p[0].lower() + p[2:] if NT else "/" + p


def para_bash(p):
    return otra_grafia(p) if NT else fw(p)


def sin_raiz(p):
    return fw(p)[3:] if NT else fw(p)[1:]


if NT:
    TEMP = "C:\\Users\\ana\\AppData\\Local\\Temp"
    ENTORNO = {"TEMP": TEMP, "TMP": TEMP, "HOME": "C:\\Users\\ana", "USERPROFILE": "C:\\Users\\ana", "SYSTEMROOT": "C:\\Windows"}
    RAIZ_SCRATCH = "C:/Users/ana/AppData/Local/Temp/claude"
    PROYECTO = "C:\\proyecto"
else:
    ENTORNO = {"HOME": "/datos/ana"}
    RAIZ_SCRATCH = "/tmp/claude-%d" % os.getuid()
    PROYECTO = "/proyecto"
AREA = RAIZ_SCRATCH + "/proy-x"
AREA_MEZCLADA = "c:/users/ANA/appdata/LOCAL/temp/Claude/proy-x" if NT else AREA.title()
SCR = AREA + "/a0b1c2d3/scratchpad"
EQUIPO_SINTETICO = "C:\\sintetico\\equipo" if NT else "/sintetico/equipo"
UNIDAD_EN_TEXTO = re.compile(r"(?i)(?<![\w/\\])[a-z]:(?=[\\/])")


def valores(equipo):
    eq = bw(equipo) if NT else str(equipo)
    return {
        "AREA": AREA, "AREA^": AREA.upper(), "AREA~": AREA_MEZCLADA, "AREAW": bw(AREA),
        "SCR": SCR, "SCRB": otra_grafia(SCR), "SCRW": bw(SCR), "SCRW^": bw(SCR).upper(),
        "EQ": eq, "EQ^": eq.upper(), "EQ_": eq.lower() if NT else eq.title(), "EQF": fw(equipo), "EQF^": fw(equipo).upper(),
        "DB": fw(equipo) + "/db",
    }


def _r(texto, tabla=None):
    if texto is None:
        return None
    if not NT:
        texto = UNIDAD_EN_TEXTO.sub("", texto)
    return texto if tabla is None else re.sub(r"«([A-Z]+[\^_~]?)»", lambda m: tabla[m.group(1)], texto)


def _cwd(texto, tabla):
    texto = _r(texto, tabla)
    return texto if texto is None or NT else texto.replace("\\", "/")


CASOS = [
    ('calentamiento: comando trivial sin heredoc', 'git status', None, 'allow'),
    ('heredoc de commit que menciona push --force', "git commit -F - <<'EOF'\nfix(guard): describe lo que hace el guard\n\nEl guard solo bloquea push --force y reset --hard.\nNo mira git commit ni el repo destino.\nEOF", None, 'allow'),
    ('echo que menciona reset --hard', 'echo "git reset --hard is dangerous"', None, 'allow'),
    ('heredoc de commit que cita un heredoc de shell', "git commit -F - <<'EOF'\nfix(guard): documenta quién recibe el heredoc\n\n  git commit -F - <<'EOF'  -> el cuerpo es TEXTO\n  bash <<'EOF'             -> el cuerpo es CODIGO\n\nVerificado: push --force, clean -fd, reset --hard siguen bloqueando.\nEOF", None, 'allow'),
    ('heredoc de bash que mete un push --force', "bash <<'EOF'\ngit push --force origin master\nEOF", None, 'block'),
    ('heredoc de sh que mete un reset --hard', "sh <<'EOF'\ngit reset --hard HEAD~5\nEOF", None, 'block'),
    ('heredoc de bash cuyo cuerpo cita un git commit', "bash <<'EOF'\n# git commit -F - <<'INNER'\ngit push --force origin master\nEOF", None, 'block'),
    ('git push --force real', 'git push --force origin master', None, 'block'),
    ('git push -f real', 'git push -f origin master', None, 'block'),
    ('git reset --hard real', 'git reset --hard HEAD~1', None, 'block'),
    ('git clean -fd real', 'git clean -fd', None, 'block'),
    ('rm -rf real fuera del scratch', 'rm -rf c:/proyecto/tickets', None, 'block'),
    ('Remove-Item -Recurse -Force real', 'Remove-Item -Recurse -Force c:/proyecto/tickets', None, 'block'),
    ('git push --force-with-lease', 'git push --force-with-lease origin master', None, 'allow'),
    ('git commit simple', 'git commit -m "fix: something"', None, 'allow'),
    ('git push simple', 'git push origin master', None, 'allow'),
    ('rm -rf dentro del scratch', 'rm -rf «AREA»/x', None, 'allow'),
    ('git status', 'git status --short', None, 'allow'),
    ('checkout de rama en un repo protegido con -C', 'git -C «EQ»\\web\\movil checkout F_beto_y', None, 'ask'),
    ('switch en un repo protegido por el cwd', 'git switch master', '«EQ»\\db', 'ask'),
    ('checkout -b en un repo protegido (también cambia de rama)', 'git -C «EQ»\\db checkout -b F_nueva', None, 'ask'),
    ('checkout con la ruta del repo protegido entre comillas', 'git -C "«EQ»\\web\\api" switch otra', None, 'ask'),
    ('un -- final suelto igual cambia de rama', 'git -C «EQ»\\db checkout master --', None, 'ask'),
    ('switch con un -- final suelto', 'git switch master --', '«EQ»\\db', 'ask'),
    ('encadenado: el -- de un diff posterior no lo tapa', 'git -C «EQ»\\db checkout master && git diff HEAD -- .', None, 'ask'),
    ('una mención de worktrees en otro lado no lo tapa', 'git -C «EQ»\\db checkout master; ls «EQ»\\worktrees', 'C:\\proyecto', 'ask'),
    ('-C al clon principal desde el cwd de un worktree pregunta', 'git -C «EQ»\\db checkout otra', '«EQ»\\worktrees\\db--x', 'ask'),
    ('encadenado: un restore primero no tapa el switch', 'git -C «EQ»\\db checkout -- x.sql && git -C «EQ»\\db checkout master', None, 'ask'),
    ('encadenado con ;: restore primero, switch después', 'git checkout -- x.sql; git switch master', '«EQ»\\db', 'ask'),
    ('--work-tree con el argumento separado pregunta', 'git --work-tree «EQ»\\db checkout master', None, 'ask'),
    ('una cadena de restores pregunta', 'git -C «EQ»\\db checkout -- a.sql; git -C «EQ»\\db checkout -- b.sql', None, 'ask'),
    ('git log --grep checkout es de lectura', 'git -C «EQ»\\db log --grep checkout', None, 'allow'),
    ('echo checkout con el cwd en un repo protegido', 'git status && echo checkout', '«EQ»\\db', 'allow'),
    ('una rama llamada checkout-* crea una rama: pregunta', 'git -C «EQ»\\db branch checkout-fix-list', None, 'ask'),
    ('restore con un pathspec entre comillas y con espacio pregunta', 'git -C «EQ»\\db checkout -- "mi archivo.sql"', None, 'ask'),
    ('checkout -- archivo en un repo protegido pregunta', 'git -C «EQ»\\db checkout -- script.sql', None, 'ask'),
    ('checkout ref -- pathspec en un repo protegido pregunta', 'git -C «EQ»\\db checkout origin/master -- Sp/x.sql', None, 'ask'),
    ('worktree add en un repo protegido', 'git -C «EQ»\\db worktree add «EQ»/worktrees/db--x origin/x', None, 'allow'),
    ('checkout dentro de un worktree pregunta', 'git checkout otra-rama', '«EQ»\\worktrees\\db--x', 'ask'),
    ('checkout fuera de los repos protegidos', 'git checkout -b feature', 'C:\\proyecto', 'allow'),
    ('heredoc de commit que menciona un checkout en un repo protegido', "git commit -F - <<'EOF'\ndocs(ramas): explica el flujo de ramas\n\nNunca correr git checkout master en «EQ»\\db con WIP.\nEOF", None, 'allow'),
    ('git push a secas en un repo protegido', 'git push', '«EQ»\\db', 'ask'),
    ('git push solo con el remoto en un repo protegido', 'git push origin', '«EQ»\\db', 'ask'),
    ('git push -u origin <rama> (la forma correcta) pregunta', 'git push -u origin F_beto_12_lector', '«EQ»\\db', 'ask'),
    ('git push origin master en un repo protegido pregunta', 'git push origin master', '«EQ»\\db', 'ask'),
    ('git push origin HEAD:master pregunta', 'git push origin HEAD:master', '«EQ»\\db', 'ask'),
    ('git push origin :master (borra master) pregunta', 'git push origin :master', '«EQ»\\db', 'ask'),
    ('git push con -C a un repo protegido y rama explícita pregunta', 'git -C «EQ»\\web\\api push -u origin F_rama', None, 'ask'),
    ('git push refs/heads/<rama> pregunta', 'git push origin HEAD:refs/heads/F_rama', '«EQ»\\db', 'ask'),
    ('encadenado: explícito primero y a secas después pregunta', 'git push -u origin F_rama && git push', '«EQ»\\db', 'ask'),
    ('encadenado: el a secas primero no lo tapa el explícito después', 'git push && git push -u origin F_rama', '«EQ»\\db', 'ask'),
    ('git push a secas fuera de los repos protegidos', 'git push', 'C:\\proyecto', 'allow'),
    ('git push en otro repo', 'git push origin main', 'C:\\otro\\repo', 'allow'),
    ('git status en un repo protegido no es un push', 'git status --short', '«EQ»\\db', 'allow'),
    ('heredoc de commit que menciona un push a secas en un repo protegido', "git commit -F - <<'EOF'\ndocs(ramas): pushear siempre con destino explicito\n\nEn «EQ» nunca correr git push a secas: la rama hereda\norigin/master como upstream y el commit se va a master.\nEOF", None, 'allow'),
    ('cp al scratch y rm -rf del original', 'cp -r c:/proyecto/tickets/T-7-ejemplo «SCR»/bk && rm -rf c:/proyecto/tickets/T-7-ejemplo', None, 'block'),
    ('echo del scratch ; rm -rf en otro lado', 'echo «SCR» ; rm -rf C:/proyecto/algo', None, 'block'),
    ('un comentario que nombra el scratch junto a un rm -rf', 'rm -rf c:/proyecto/tickets # «SCR»', None, 'block'),
    ('una mención del scratch entre comillas junto a un rm -rf', 'rm -rf c:/proyecto/tickets && echo "«SCR»"', None, 'block'),
    ('<area>/../../x cae fuera del área', 'rm -rf «AREA»/../../algo', None, 'block'),
    ('<scratch>/.. nueve veces cae en el proyecto', 'rm -rf «SCR»/../../../../../../../../../proyecto', None, 'block'),
    ('un rm -rf con un destino en el scratch y otro en el proyecto', 'rm -rf «SCR»/tmp c:/proyecto/tickets', None, 'block'),
    ('un borrado escondido en $() antes de un rm del scratch', 'echo $(rm -rf c:/proyecto/tickets) && rm «SCR»/x.txt', None, 'block'),
    ('forma de Git Bash: copia y rm -rf de /c/proyecto', 'cp -r /c/proyecto/tickets/x «SCRB»/bk; rm -rf /c/proyecto/tickets/x', None, 'block'),
    ('un destino por variable falla cerrado', 'SP=«SCR»; rm -rf $SP/x', None, 'block'),
    ('Remove-Item del proyecto ; ls del scratch', 'Remove-Item -Recurse -Force c:/proyecto/docs; ls «SCRW»', None, 'block'),
    ('Copy-Item al scratch ; Remove-Item del original', 'Copy-Item -Recurse c:/proyecto/tickets/T-7-ejemplo «SCRW»\\bk; Remove-Item -Recurse -Force c:/proyecto/tickets/T-7-ejemplo', None, 'block'),
    ('comentario de PowerShell que nombra el scratch', 'Remove-Item -Recurse -Force c:\\proyecto\\tickets # «SCRW»', None, 'block'),
    ('Write-Output del scratch ; Remove-Item en otro lado', 'Write-Output "«SCRW»"; Remove-Item -Recurse -Force C:\\proyecto\\algo', None, 'block'),
    ('<area>\\..\\..\\x de PowerShell cae fuera', 'Remove-Item -Recurse -Force «AREAW»\\..\\..\\algo', None, 'block'),
    ('lista de -Path con un destino fuera', 'Remove-Item -Path «SCRW»\\a,C:\\proyecto\\tickets -Recurse -Force', None, 'block'),
    ('un pipe hacia Remove-Item falla cerrado', 'Get-ChildItem C:\\proyecto\\tickets | Remove-Item -Recurse -Force «SCRW»\\x', None, 'block'),
    ('rm -rf <scratch>/tmp', 'rm -rf «SCR»/tmp', None, 'allow'),
    ('ruta del scratch con espacio entre comillas dobles', 'rm -rf "«SCR»/tmp dir"', None, 'allow'),
    ('ruta del scratch entre comillas simples', "rm -rf '«SCR»/tmp'", None, 'allow'),
    ('forma /c/Users de Git Bash', 'rm -rf «SCRB»/tmp', None, 'allow'),
    ('ruta sin distinguir mayúsculas', 'rm -rf «AREA~»/x', None, 'allow'),
    ('dos destinos del scratch y 2>/dev/null', 'rm -rf «SCR»/a «SCRB»/b 2>/dev/null', None, 'allow'),
    ('cp DESDE el proyecto y rm -rf solo del scratch', 'cp -r c:/proyecto/tickets/T-7-ejemplo «SCR»/bk && rm -rf «SCR»/old', None, 'allow'),
    ('ruta del scratch con espacio entre comillas en PowerShell', 'Remove-Item -Recurse -Force "«SCRW»\\tmp dir"', None, 'allow'),
    ('-LiteralPath con el valor de -ErrorAction', "Remove-Item -LiteralPath '«SCRW»\\x' -Recurse -Force -ErrorAction SilentlyContinue", None, 'allow'),
    ('forma con barras invertidas, sin comillas', 'Remove-Item -Recurse -Force «SCRW»\\tmp', None, 'allow'),
    ('GIT PUSH --FORCE en mayúsculas', 'GIT PUSH --FORCE ORIGIN MASTER', None, 'block'),
    ('Git Push -F', 'Git Push -F origin x', None, 'block'),
    ('Git Reset --Hard', 'Git Reset --Hard HEAD~1', None, 'block'),
    ('GIT CLEAN -FD', 'GIT CLEAN -FD', None, 'block'),
    ('RM -RF fuera del scratch', 'RM -RF c:/proyecto/x', None, 'block'),
    ('remove-item -recurse -force en minúsculas', 'remove-item -recurse -force c:/proyecto/x', None, 'block'),
    ('REMOVE-ITEM -RECURSE -FORCE en mayúsculas', 'REMOVE-ITEM -RECURSE -FORCE C:\\proyecto\\X', None, 'block'),
    ('Ri -Force -Recurse', 'Ri -Force -Recurse c:/proyecto/x', None, 'block'),
    ('heredoc de BASH que mete un GIT PUSH --FORCE', "BASH <<'EOF'\nGIT PUSH --FORCE ORIGIN MASTER\nEOF", None, 'block'),
    ('PUSH de MASTER con -C en mayúsculas', 'GIT -C «EQF^»/DB PUSH ORIGIN MASTER', None, 'ask'),
    ('Git Push a secas con el cwd en mayúsculas', 'Git Push', '«EQ^»\\DB', 'ask'),
    ('Git Checkout en un repo protegido', 'Git Checkout F_x', '«EQ»\\db', 'ask'),
    ('GIT SWITCH con la ruta de -C en minúsculas', 'GIT -C «EQ_»\\web\\movil SWITCH MASTER', None, 'ask'),
    ('GIT PUSH --FORCE-WITH-LEASE', 'GIT PUSH --FORCE-WITH-LEASE ORIGIN X', None, 'allow'),
    ('Git Push -U origin <rama> pregunta', 'Git Push -U origin F_beto_x', '«EQ»\\db', 'ask'),
    ('Git Checkout -- X.SQL pregunta', 'Git -C «EQ»\\db Checkout -- X.SQL', None, 'ask'),
    ('checkout con el cwd de un worktree en mayúsculas pregunta', 'git checkout otra', '«EQ^»\\WORKTREES\\DB--x', 'ask'),
    ('RM -RF del scratch en mayúsculas', 'RM -RF «AREA^»/X', None, 'allow'),
    ('REMOVE-ITEM del scratch en mayúsculas', 'REMOVE-ITEM -Recurse -FORCE «SCRW^»\\TMP', None, 'allow'),
    ('heredoc de GIT COMMIT que menciona PUSH --FORCE', "GIT COMMIT -F - <<'EOF'\ndocs: GIT PUSH --FORCE y RM -RF siguen bloqueados\nEOF", None, 'allow'),
    ('push origin +master es un push forzado', 'git push origin +master', None, 'block'),
    ('push +<rama> fuera de los repos protegidos también', 'git push origin +F_rama', 'C:\\otro\\repo', 'block'),
    ('push -u origin +<rama> en un repo protegido', 'git push -u origin +F_rama', '«EQ»\\db', 'block'),
    ('el bloque -uf es un push forzado', 'git push -uf origin F_rama', None, 'block'),
    ('el lease de OTRO push no cubre el +', 'git push --force-with-lease origin F_a && git push origin +F_b', None, 'block'),
    ('--force-with-lease con refspec + (el lease sigue mirándose)', 'git push --force-with-lease origin +F_rama', None, 'allow'),
    ('lease y +master en un repo protegido igual pregunta (master)', 'git push --force-with-lease origin +master', '«EQ»\\db', 'ask'),
    ('push refs/heads/master pregunta', 'git push origin refs/heads/master', '«EQ»\\db', 'ask'),
    ('push HEAD:refs/heads/master pregunta', 'git push origin HEAD:refs/heads/master', '«EQ»\\db', 'ask'),
    ('push master:refs/heads/master pregunta', 'git push origin master:refs/heads/master', '«EQ»\\db', 'ask'),
    ('push HEAD:heads/master (DWIM de git) pregunta', 'git push origin HEAD:heads/master', '«EQ»\\db', 'ask'),
    ('push HEAD:Master pregunta (control)', 'git push origin HEAD:Master', '«EQ»\\db', 'ask'),
    ('master como segundo refspec pregunta', 'git push -u origin F_x master', '«EQ»\\db', 'ask'),
    ('un refspec entre comillas es un destino desconocido', 'git push origin "HEAD:master"', '«EQ»\\db', 'ask'),
    ('un refspec en una sustitución es desconocido', 'git push -u origin $(git branch --show-current)', '«EQ»\\db', 'ask'),
    ('HEAD solo es la rama actual, puede ser master', 'git push -u origin HEAD', '«EQ»\\db', 'ask'),
    ('un refspec con comodín puede llegar a master', 'git push origin refs/heads/*:refs/heads/*', '«EQ»\\db', 'ask'),
    ('master después de una continuación de línea', 'git push -u origin \\\nmaster', '«EQ»\\db', 'ask'),
    ('push --mirror pregunta (control)', 'git push --mirror origin', '«EQ»\\db', 'ask'),
    ('-o con valor y después master pregunta', 'git push -o ci.skip origin master', '«EQ»\\db', 'ask'),
    ('-o con valor y solo el remoto pregunta', 'git push -o ci.skip origin', '«EQ»\\db', 'ask'),
    ('--push-option con valor y rama explícita pregunta', 'git push --push-option ci.skip -u origin F_rama', '«EQ»\\db', 'ask'),
    ('push origin 2>&1 es solo el remoto', 'git push origin 2>&1', '«EQ»\\db', 'ask'),
    ('push origin 2>/dev/null es solo el remoto', 'git push origin 2>/dev/null', '«EQ»\\db', 'ask'),
    ('la forma correcta con 2>&1 pregunta', 'git push -u origin F_beto_x 2>&1', '«EQ»\\db', 'ask'),
    ('push origin :<rama-ajena> la borra', 'git push origin :F_ana_x', '«EQ»\\db', 'ask'),
    ('push --delete <rama> pregunta', 'git push origin --delete F_otra', '«EQ»\\db', 'ask'),
    ('push -d <rama> pregunta', 'git push -d origin F_otra', '«EQ»\\db', 'ask'),
    ('push --delete fuera de los repos protegidos pasa', 'git push origin --delete vieja', 'C:\\otro\\repo', 'allow'),
    ('heredoc de commit que menciona +master: el commit pregunta', "git commit -F - <<'EOF'\nfix: git push origin +master es un force push\nEOF", '«EQ»\\db', 'ask'),
    ('rm -r sin -f', 'rm -r c:/proyecto/tickets', None, 'block'),
    ('rm -R', 'rm -R c:/proyecto/tickets', None, 'block'),
    ('rm --recursive', 'rm --recursive c:/proyecto/tickets', None, 'block'),
    ('/usr/bin/rm -rf (ruta al binario)', '/usr/bin/rm -rf c:/proyecto/tickets', None, 'block'),
    ('rm -rf dentro de $()', 'echo $(rm -rf c:/proyecto/tickets)', None, 'block'),
    ('rm -rf dentro de ( )', '(rm -rf c:/proyecto/tickets)', None, 'block'),
    ('xargs rm -r', 'ls c:/proyecto/tickets | xargs rm -r', None, 'block'),
    ('find -exec rm -r', 'find c:/proyecto/tickets -name x -exec rm -r {} +', None, 'block'),
    ('Remove-Item -Recurse sin -Force', 'Remove-Item -Recurse c:/proyecto/tickets', None, 'block'),
    ('Remove-Item -r -fo (abreviado)', 'Remove-Item c:/proyecto/tickets -r -fo', None, 'block'),
    ('rd -Recurse -Force', 'rd c:/proyecto/tickets -Recurse -Force', None, 'block'),
    ('rmdir -Recurse -Force', 'rmdir c:\\proyecto\\tickets -Recurse -Force', None, 'block'),
    ('erase -Recurse', 'erase c:\\proyecto\\tickets -Recurse', None, 'block'),
    ('cmd /c rd /s /q', 'cmd /c rd /s /q c:\\proyecto\\tickets', None, 'block'),
    ('del /s /q', 'del /s /q c:\\proyecto\\tickets\\*.md', None, 'block'),
    ('gci -Recurse | Remove-Item', 'Get-ChildItem c:/proyecto/tickets -Recurse -File | Remove-Item', None, 'block'),
    ('ForEach-Object { Remove-Item -Recurse }', 'Get-ChildItem c:/proyecto/tickets | ForEach-Object { Remove-Item $_ -Recurse }', None, 'block'),
    ('%{Remove-Item -r} (el alias pegado a su bloque)', 'Get-ChildItem c:/proyecto/tickets | %{Remove-Item $_ -r}', None, 'block'),
    ('if/then rm -r', 'if [ -d c:/proyecto/x ]; then rm -r c:/proyecto/x; fi', None, 'block'),
    ('git rm -r --cached no es un borrado', 'git rm -r --cached tickets/x', None, 'allow'),
    ('git -C <repo protegido> rm -r --cached pregunta (ni borrado ni lectura)', 'git -C «EQ»\\db rm -r --cached Sp/x', None, 'ask'),
    ('grep -r no es rm', 'grep -r rm .', None, 'allow'),
    ('grep -rn con la mención entre comillas', 'grep -rn "rm -rf" c:/proyecto/.claude', None, 'allow'),
    ('echo que menciona rm -r sin -f', 'echo rm -r x', None, 'allow'),
    ('rmdir sin -r (solo una carpeta vacía)', 'rmdir c:/proyecto/vacio', None, 'allow'),
    ('rmdir de PowerShell sin -Recurse', 'rmdir c:\\proyecto\\vacio', None, 'allow'),
    ('rm de un archivo', 'rm c:/proyecto/x.txt', None, 'allow'),
    ('rm -r dentro del scratch', 'rm -r «SCR»/tmp', None, 'allow'),
    ('Remove-Item -Recurse dentro del scratch', 'Remove-Item -Recurse «SCRW»\\tmp', None, 'allow'),
    ('heredoc de commit que menciona rm -r y +master', "git commit -F - <<'EOF'\ndocs: rm -r y push origin +master ahora bloquean\nEOF", None, 'allow'),
    ('commit con $(cat heredoc) que menciona rm -r', 'git commit -m "$(cat <<\'EOF\'\nfix: rm -r c:/proyecto y Remove-Item -Recurse\nEOF\n)"', None, 'allow'),
    ('git clean -d --force', 'git clean -d --force', None, 'block'),
    ('git clean --force', 'git clean --force', None, 'block'),
    ('git clean -n es una prueba en seco', 'git clean -nd', None, 'allow'),
    ('restore . en un repo protegido', 'git restore .', '«EQ»\\web\\movil', 'ask'),
    ('restore -- . con -C', 'git -C «EQ»\\web\\movil restore -- .', None, 'ask'),
    ('restore :/ (la raíz del repo)', 'git restore :/', '«EQ»\\db', 'ask'),
    ('restore --staged --worktree .', 'git restore --staged --worktree .', '«EQ»\\db', 'ask'),
    ('restore --source HEAD~1 .', 'git restore --source HEAD~1 .', '«EQ»\\db', 'ask'),
    ('restore de la ruta raíz del repo', 'git restore «EQF»/web/api', '«EQ»\\web\\api', 'ask'),
    ('restore con un glob', 'git restore *.java', '«EQ»\\web\\movil', 'ask'),
    ('restore . dentro de un worktree', 'git restore .', '«EQ»\\worktrees\\db--x', 'ask'),
    ('checkout -- . en un repo protegido', 'git checkout -- .', '«EQ»\\db', 'ask'),
    ('checkout HEAD -- . con -C', 'git -C «EQ»\\db checkout HEAD -- .', None, 'ask'),
    ('checkout origin/master -- *', 'git checkout origin/master -- *', '«EQ»\\db', 'ask'),
    ('stash drop en un repo protegido', 'git stash drop', '«EQ»\\web\\movil', 'ask'),
    ('stash clear con -C', 'git -C «EQ»\\db stash clear', None, 'ask'),
    ('restore --staged . pregunta', 'git restore --staged .', '«EQ»\\db', 'ask'),
    ('restore de un archivo pregunta', 'git restore Sp/x.sql', '«EQ»\\db', 'ask'),
    ('restore -- de un archivo con -C pregunta', 'git -C «EQ»\\db restore -- Sp/x.sql', None, 'ask'),
    ('stash y stash pop preguntan', 'git stash && git stash pop', '«EQ»\\db', 'ask'),
    ('restore . fuera de los repos protegidos', 'git restore .', 'C:\\proyecto', 'allow'),
    ('stash drop fuera de los repos protegidos', 'git stash drop', 'C:\\proyecto', 'allow'),
    ('(cd <repo protegido> && git push origin master)', '(cd «DB» && git push origin master)', None, 'ask'),
    ('(git -C <repo protegido> push -u origin master)', '(git -C «DB» push -u origin master)', None, 'ask'),
    ('echo $(git push origin master)', 'echo $(git push origin master)', '«EQ»\\db', 'ask'),
    ('push origin master>push.log', 'git push origin master>push.log', '«EQ»\\db', 'ask'),
    ('(cd <repo protegido> && git restore .)', '(cd «EQF»/web/movil && git restore .)', None, 'ask'),
    ('(git -C <repo protegido> checkout -- .)', '(git -C «DB» checkout -- .)', None, 'ask'),
    ('(cd && git push ... --force)', '(cd C:/proyecto && git push origin F_x --force)', None, 'block'),
    ('(cd && git reset --hard)', '(cd C:/proyecto && git reset --hard)', None, 'block'),
    ('git reset --hard&& git status', 'git reset --hard&& git status', None, 'block'),
    ('git clean -fd;ls', 'git clean -fd;ls', None, 'block'),
    ('(cd && git clean -fdx)', '(cd C:/proyecto && git clean -fdx)', None, 'block'),
    ('la forma correcta del push dentro de ( ) pregunta', '(cd «DB» && git push -u origin F_beto_x)', None, 'ask'),
    ('la forma correcta con >log pegado pregunta', 'git push -u origin F_beto_x>push.log', '«EQ»\\db', 'ask'),
    ('--force-with-lease --force', 'git push --force-with-lease --force origin F_ana_x', '«EQ»\\db', 'block'),
    ('--force-with-lease -f', 'git push --force-with-lease -f origin F_b', None, 'block'),
    ('--no-force-with-lease cancela el lease', 'git push --force-with-lease --no-force-with-lease origin +F_b', None, 'block'),
    ('el lease sobre F_a no cubre +F_b', 'git push --force-with-lease=F_a origin +F_b', 'C:\\otro\\repo', 'block'),
    ('lease sobre la misma ref pasa', 'git push --force-with-lease=F_rama origin +F_rama', None, 'allow'),
    ('lease refs/heads/<ref>:<esperado> sobre la misma ref pasa', 'git push --force-with-lease=refs/heads/F_rama:abc123 origin +F_rama', None, 'allow'),
    ('git reset --ha', 'git reset --ha HEAD~1', None, 'block'),
    ('git reset --h', 'git reset --h', None, 'block'),
    ('git clean -d --fo', 'git clean -d --fo', None, 'block'),
    ('git clean -d --f', 'git clean -d --f', None, 'block'),
    ('git reset --soft pasa', 'git reset --soft HEAD~1', None, 'allow'),
    ('clean en seco y log --follow pasan', 'git clean -nd; git log --follow x', None, 'allow'),
    ('if(){Remove-Item -Recurse} pegado', 'if (Test-Path c:\\proyecto\\tickets){Remove-Item c:\\proyecto\\tickets -Recurse}', None, 'block'),
    ('ForEach-Object{Remove-Item -Recurse} pegado', 'Get-ChildItem c:\\proyecto\\tickets | ForEach-Object{Remove-Item $_.FullName -Recurse}', None, 'block'),
    ('foreach(){Remove-Item -Recurse} pegado', 'foreach($d in Get-ChildItem c:\\proyecto\\tickets){Remove-Item $d.FullName -Recurse}', None, 'block'),
    ('cmd rd /q/s (switches agrupados)', 'cmd /c rd /q/s c:\\proyecto\\tickets', None, 'block'),
    ('cmd del /q/s (switches agrupados)', 'cmd /c del /q/s c:\\proyecto\\tickets\\*.md', None, 'block'),
    ('eval rm -r', 'eval rm -r c:/proyecto/tickets', None, 'block'),
    ('powershell -Command Remove-Item -Recurse sin comillas', 'powershell -NoProfile -Command Remove-Item c:/proyecto/tickets -Recurse', None, 'block'),
    ('winpty rm -r', 'winpty rm -r c:/proyecto/tickets', None, 'block'),
    ('operador punto . Remove-Item -Recurse', '. Remove-Item c:\\proyecto\\tickets -Recurse', None, 'block'),
    ('cmd rd /q sin /s pasa', 'cmd /c rd /q c:\\proyecto\\vacio', None, 'allow'),
    ('/s es una ruta para rm (la unidad S de Git Bash)', 'rm /s/tmp/x.txt', None, 'allow'),
    ('eval git rm -r --cached pasa', 'eval git rm -r --cached tickets/x', None, 'allow'),
    ('powershell -Command git rm -r --cached pasa', 'powershell -Command git rm -r --cached tickets/x', None, 'allow'),
    ('xargs git rm -r --cached pasa', 'git ls-files -i -c --exclude-standard | xargs git rm -r --cached', None, 'allow'),
    ("un argumento '.' no es el operador punto", 'git -C . rm -r --cached tickets/x', None, 'allow'),
    ('checkout . en un worktree', 'git checkout .', '«EQ»\\worktrees\\db--x', 'ask'),
    ('checkout HEAD . en un worktree', 'git checkout HEAD .', '«EQ»\\worktrees\\db--x', 'ask'),
    ('-C a un worktree checkout .', 'git -C «EQF»/worktrees/db--x checkout .', None, 'ask'),
    ('checkout -f en un worktree', 'git checkout -f', '«EQ»\\worktrees\\db--x', 'ask'),
    ('switch en un worktree pregunta', 'git switch otra', '«EQ»\\worktrees\\db--x', 'ask'),
    ('worktree remove --force en un repo protegido', 'git -C «DB» worktree remove --force «EQF»/worktrees/db--x', None, 'ask'),
    ('worktree remove -f en un repo protegido', 'git worktree remove -f ../worktrees/db--x', '«EQ»\\db', 'ask'),
    ('worktree remove sin --force pregunta', 'git -C «DB» worktree remove «EQF»/worktrees/db--x', None, 'ask'),
    ('worktree remove --force fuera de los repos protegidos pasa', 'git worktree remove --force ../x', 'C:\\otro\\repo', 'allow'),
    ('receta: fetch origin', 'git -C «DB» fetch origin', None, 'allow'),
    ('receta: status --short en el worktree', 'git -C «EQF»/worktrees/db--F_x status --short', None, 'allow'),
    ('receta: worktree list', 'git -C «DB» worktree list', None, 'allow'),
    ('receta: log --oneline origin/<rama>..<rama>', 'git -C «DB» log --oneline origin/F_beto_x..F_beto_x', None, 'allow'),
    ('receta: rev-parse <rama>@{upstream}', 'git -C «DB» rev-parse --abbrev-ref F_beto_x@{upstream}', None, 'allow'),
    ('receta: ls-tree -r --name-only origin/<rama>', 'git -C «DB» ls-tree -r --name-only origin/F_beto_x', None, 'allow'),
    ('receta: show origin/<rama>:<ruta> | diff', 'git -C «DB» show origin/F_x:Current/x.sql | diff -qw --strip-trailing-cr - c:/proyecto/tickets/T-7-ejemplo/SQL/x.sql', None, 'allow'),
    ('receta: diff de un archivo del ambiente', 'git -C «EQF»/web/api diff -- Worker.cs', None, 'allow'),
    ('receta: fetch && status encadenados', 'git -C «DB» fetch origin && git -C «DB» status --short', None, 'allow'),
    ('log --oneline -5 con -C', 'git -C «DB» log --oneline -5', None, 'allow'),
    ('diff --stat con el cwd en un repo protegido', 'git diff --stat', '«EQ»\\web\\api', 'allow'),
    ('show HEAD:<ruta>', 'git show HEAD:Sp/x.sql', '«EQ»\\db', 'allow'),
    ("grep -n x origin/master -- '*.sql'", "git grep -n x origin/master -- '*.sql'", '«EQ»\\db', 'allow'),
    ('branch -a --contains x', 'git branch -a --contains abc123', '«EQ»\\db', 'allow'),
    ('for-each-ref --format', "git for-each-ref --format='%(refname:short) %(upstream:short)' refs/heads", '«EQ»\\db', 'allow'),
    ('cat-file -p', 'git cat-file -p HEAD:Sp/x.sql', '«EQ»\\db', 'allow'),
    ('blame -L', 'git blame -L 10,20 Sp/x.sql', '«EQ»\\db', 'allow'),
    ('(cd <repo protegido> && git log)', '(cd «DB» && git log --oneline -3)', None, 'allow'),
    ('log | head, 2>&1', 'git log --oneline -20 2>&1 | head -5', '«EQ»\\db', 'allow'),
    ('opciones globales --no-pager y -P', 'git --no-pager log -1 && git -P diff --name-only', '«EQ»\\db', 'allow'),
    ('formas de listar ramas', "git branch -vv; git branch --show-current; git branch --list 'F_*'", '«EQ»\\db', 'allow'),
    ('tag -l, stash list/show, reflog y notes', "git tag -l 'v*'; git stash list; git stash show -p stash@{0}; git reflog -10; git notes list", '«EQ»\\db', 'allow'),
    ('remote -v / show, config --get/--list', 'git remote -v; git remote show origin; git config --get remote.origin.url; git config --list --show-origin', '«EQ»\\db', 'allow'),
    ('--version, help, rev-list y merge-base', 'git --version; git help log; git rev-list --count HEAD; git merge-base HEAD origin/master', '«EQ»\\db', 'allow'),
    ('asignación de PowerShell desde git', '$f = git -C «DB» ls-files; $f.Count', None, 'allow'),
    ('foreach de PowerShell sobre los repos', 'foreach ($r in \'db\',\'web\\movil\') { git -C "«EQ»\\$r" status --short }', None, 'allow'),
    ('git log --grep=git no es un git anidado', 'git log --grep=git -5', '«EQ»\\db', 'allow'),
    ('commit -m en el proyecto que menciona la ruta protegida', 'git add README.md && git commit -m "docs: «EQ» es del equipo"', 'C:\\proyecto', 'allow'),
    ('-C al proyecto: commit desde el cwd de un repo protegido', 'git -C C:/proyecto commit -m x', '«EQ»\\db', 'allow'),
    ('commit en el proyecto con un here-string que nombra la ruta protegida', "git commit -m @'\ndocs: no commitear en «EQ»\\db (it's theirs)\n'@", 'C:\\proyecto', 'allow'),
    ('mensaje de commit no ASCII en el proyecto', 'git commit -m "docs: sesión, año, ñandú"', 'C:\\proyecto', 'allow'),
    ('commit no ASCII en un repo protegido pregunta', 'git commit -m "fix: sesión"', '«EQ»\\web\\movil', 'ask'),
    ('ruta no ASCII en un borrado recursivo bloquea', 'rm -rf c:/proyecto/Año', None, 'block'),
    ('fuera de los repos protegidos no cambia nada', 'git commit -m x && git st && git stash drop', 'C:\\proyecto', 'allow'),
    ('commit', 'git commit -m "fix: x"', '«EQ»\\db', 'ask'),
    ('add', 'git add Sp/x.sql', '«EQ»\\db', 'ask'),
    ('push -u origin HEAD', 'git push -u origin HEAD', '«EQ»\\db', 'ask'),
    ('push --tags', 'git push origin --tags', '«EQ»\\db', 'ask'),
    ('merge', 'git merge origin/master', '«EQ»\\db', 'ask'),
    ('rebase', 'git rebase origin/master', '«EQ»\\db', 'ask'),
    ('cherry-pick', 'git cherry-pick abc123', '«EQ»\\db', 'ask'),
    ('revert', 'git revert abc123', '«EQ»\\db', 'ask'),
    ('pull', 'git pull', '«EQ»\\db', 'ask'),
    ('tag nuevo', 'git tag v1.0', '«EQ»\\db', 'ask'),
    ('tag -a', 'git tag -a v1 -m x', '«EQ»\\db', 'ask'),
    ('checkout <rama>', 'git checkout F_x', '«EQ»\\db', 'ask'),
    ('switch -c', 'git switch -c F_nueva', '«EQ»\\db', 'ask'),
    ('restore', 'git restore Sp/x.sql', '«EQ»\\db', 'ask'),
    ('reset (mixed)', 'git reset HEAD~1', '«EQ»\\db', 'ask'),
    ('reset --soft', 'git reset --soft HEAD~1', '«EQ»\\db', 'ask'),
    ('reset -- <ruta>', 'git reset -- Sp/x.sql', '«EQ»\\db', 'ask'),
    ('stash (a secas es push)', 'git stash', '«EQ»\\db', 'ask'),
    ('stash -u', 'git stash -u', '«EQ»\\db', 'ask'),
    ('stash drop', 'git stash drop', '«EQ»\\db', 'ask'),
    ('stash pop', 'git stash pop', '«EQ»\\db', 'ask'),
    ('stash apply', 'git stash apply', '«EQ»\\db', 'ask'),
    ('stash clear', 'git stash clear', '«EQ»\\db', 'ask'),
    ('branch -D', 'git branch -D F_x', '«EQ»\\db', 'ask'),
    ('branch nueva', 'git branch F_nueva', '«EQ»\\db', 'ask'),
    ('branch -m', 'git branch -m F_a F_b', '«EQ»\\db', 'ask'),
    ('branch -a <nombre> no es un patrón de lista', 'git branch -a F_x', '«EQ»\\db', 'ask'),
    ('branch --set-upstream-to', 'git branch --set-upstream-to=origin/F_x', '«EQ»\\db', 'ask'),
    ('branch -u', 'git branch -u origin/F_x', '«EQ»\\db', 'ask'),
    ('tag -d', 'git tag -d v1', '«EQ»\\db', 'ask'),
    ('worktree remove', 'git worktree remove ../worktrees/db--x', '«EQ»\\db', 'ask'),
    ('worktree prune', 'git worktree prune', '«EQ»\\db', 'ask'),
    ('worktree move', 'git worktree move a b', '«EQ»\\db', 'ask'),
    ('worktree add -B reinicia una rama', 'git worktree add -B F_x «EQF»/worktrees/db--F_x origin/master', '«EQ»\\db', 'ask'),
    ('config <clave> <valor>', 'git config user.name x', '«EQ»\\db', 'ask'),
    ('config --unset', 'git config --unset core.x', '«EQ»\\db', 'ask'),
    ('config --get junto a --add', 'git config --get a.b --add c.d e', '«EQ»\\db', 'ask'),
    ('remote add', 'git remote add x https://h/x', '«EQ»\\db', 'ask'),
    ('remote remove', 'git remote remove x', '«EQ»\\db', 'ask'),
    ('remote set-url', 'git remote set-url origin https://h/x', '«EQ»\\db', 'ask'),
    ('reflog expire', 'git reflog expire --expire=now --all', '«EQ»\\db', 'ask'),
    ('gc', 'git gc', '«EQ»\\db', 'ask'),
    ('prune', 'git prune', '«EQ»\\db', 'ask'),
    ('update-ref', 'git update-ref refs/heads/x HEAD', '«EQ»\\db', 'ask'),
    ('notes add', 'git notes add -m x', '«EQ»\\db', 'ask'),
    ('rm --cached', 'git -C «DB» rm --cached x', None, 'ask'),
    ('diff --output', 'git -C «DB» diff --output=C:/x.patch', None, 'ask'),
    ('diff --outp (abreviado)', 'git diff --outp=x.patch', '«EQ»\\db', 'ask'),
    ('grep -O', 'git grep -O x', '«EQ»\\db', 'ask'),
    ('grep -Ovim (pegado)', 'git grep -nOvim x', '«EQ»\\db', 'ask'),
    ('grep --open-files-in-pager', 'git grep --open-files-in-pager=vim x', '«EQ»\\db', 'ask'),
    ('diff --ext-diff', 'git diff --ext-diff', '«EQ»\\db', 'ask'),
    ('log --ext (abreviado)', 'git log -p --ext', '«EQ»\\db', 'ask'),
    ('ls-remote --upload-pack', 'git ls-remote --upload-pack=x origin', '«EQ»\\db', 'ask'),
    ('fetch --upload-pack', 'git fetch --upload-pack x origin', '«EQ»\\db', 'ask'),
    ('fetch -u', 'git fetch -u origin', '«EQ»\\db', 'ask'),
    ('fetch --update-head-ok', 'git fetch --update-head-ok origin', '«EQ»\\db', 'ask'),
    ('fetch <origen>:<destino> escribe una rama local', 'git fetch origin master:master', '«EQ»\\db', 'ask'),
    ('fetch --refmap=<origen>:<destino>', 'git fetch --refmap=+refs/heads/*:refs/heads/* origin master', '«EQ»\\db', 'ask'),
    ('fetch --set-upstream (la trampa del upstream en master)', 'git fetch --set-upstream origin master', '«EQ»\\db', 'ask'),
    ('fetch --stdin / -P', 'git fetch --stdin origin; git fetch -P', '«EQ»\\db', 'ask'),
    ('fetch --prune sigue siendo de lectura', 'git fetch --prune origin', '«EQ»\\db', 'allow'),
    ('git -c alias', "git -c alias.x='!echo hola' x", '«EQ»\\db', 'ask'),
    ('git -c antes de una lectura', 'git -c core.pager=less log', '«EQ»\\db', 'ask'),
    ('--config-env', 'git --config-env=core.pager=PG log', '«EQ»\\db', 'ask'),
    ('--exec-path', 'git --exec-path=C:/x log', '«EQ»\\db', 'ask'),
    ('opción global desconocida', 'git --namespace=x log', '«EQ»\\db', 'ask'),
    ('variables GIT_CONFIG_* (equivalen a -c)', 'GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.pager GIT_CONFIG_VALUE_0=x git log', '«EQ»\\db', 'ask'),
    ('$env:GIT_EXTERNAL_DIFF', "$env:GIT_EXTERNAL_DIFF = 'x'; git diff", '«EQ»\\db', 'ask'),
    ('alias desconocido', 'git st', '«EQ»\\db', 'ask'),
    ('git por variable', '$g push origin F_x', '«EQ»\\db', 'ask'),
    ('git por variable asignada en el mismo comando', 'g=git; $g push -u origin F_x', '«EQ»\\db', 'ask'),
    ('& $g push (PowerShell)', '& $g push origin F_x', '«EQ»\\db', 'ask'),
    ('env $g push (variable después de un envoltorio)', 'env $g push origin F_x', '«EQ»\\db', 'ask'),
    ('"$(command -v git)" push', '"$(command -v git)" push origin F_x', '«EQ»\\db', 'ask'),
    ('Set-Alias a git', 'Set-Alias g git; g push origin F_x', '«EQ»\\db', 'ask'),
    ('heredoc pasado por un pipe a bash', "cat <<'EOF' | bash\ngit -C «DB» push -u origin F_x\nEOF", 'C:\\proyecto', 'ask'),
    ('push HACIA el repo protegido como remoto con ruta entre comillas', 'git push "«DB»" master:F_x', 'C:\\proyecto', 'ask'),
    ('git.exe push', 'git.exe push -u origin F_x', '«EQ»\\db', 'ask'),
    ('& git push (PowerShell)', '& git push -u origin F_x', '«EQ»\\db', 'ask'),
    ('& <ruta>\\git.exe push', '& "C:\\Program Files\\Git\\cmd\\git.exe" push -u origin F_x', '«EQ»\\db', 'ask'),
    ('/usr/bin/git push', '/usr/bin/git push -u origin F_x', '«EQ»\\db', 'ask'),
    ('xargs git checkout', 'git ls-files | xargs git checkout --', '«EQ»\\db', 'ask'),
    ('find -exec git checkout', "find . -name '*.sql' -exec git checkout -- {} \\;", '«EQ»\\db', 'ask'),
    ('bash -c con un git de escritura entre comillas', 'bash -c "git -C «DB» push -u origin F_x"', 'C:\\proyecto', 'ask'),
    ('powershell -Command con un git de escritura entre comillas', "powershell -NoProfile -Command 'git commit -m x'", '«EQ»\\db', 'ask'),
    ('git dentro de un $( ) entre comillas', 'echo "$(git -C «DB» commit -m x)"', 'C:\\proyecto', 'ask'),
    ('x=$(git push)', 'out=$(git push -u origin F_x)', '«EQ»\\db', 'ask'),
    ('sustitución anidada después de una lectura', 'git log $(git push -u origin F_x)', '«EQ»\\db', 'ask'),
    ('lectura y escritura encadenadas', 'git status; git commit -m x', '«EQ»\\db', 'ask'),
    ('escritura escondida detrás de comillas escapadas', 'echo \\"; git push -u origin F_x; echo \\"', '«EQ»\\db', 'ask'),
    ('commit con here-string en un repo protegido pregunta (como commit)', "git commit -m @'\nfix: x\n'@", '«EQ»\\db', 'ask'),
    ('un apóstrofo en un here-string no esconde el push que sigue', "git -C C:/proyecto commit -m @'\ndon't\n'@; git -C «DB» push -u origin F_x", 'C:\\proyecto', 'ask'),
    ('Invoke-Expression de un here-string', "Invoke-Expression @'\ngit -C «EQ»\\db push -u origin F_x\n'@", 'C:\\proyecto', 'ask'),
    ('cd al repo protegido por una variable', 'R=«DB»; cd $R && git push -u origin F_x', 'C:\\proyecto', 'ask'),
    ('(cd <repo protegido> && git push origin master) otra vez', '(cd «DB» && git push origin master)', None, 'ask'),
    ('checkout . en un worktree otra vez', 'git checkout .', '«EQ»\\worktrees\\db--x', 'ask'),
    ('worktree remove --force con -C', 'git -C «DB» worktree remove --force «EQF»/worktrees/db--x', None, 'ask'),
    ('reset --ha en un repo protegido igual bloquea', 'git reset --ha', '«EQ»\\db', 'block'),
    ('push --force en un repo protegido igual bloquea', 'git -C «DB» push --force origin F_x', None, 'block'),
    ('clean -fd en un repo protegido igual bloquea', 'git clean -fd', '«EQ»\\db', 'block'),
    ('rm -rf de una ruta protegida igual bloquea', 'rm -rf «DB»/Sp', 'C:\\proyecto', 'block'),
]


def evento(comando, cwd=None, herramienta="Bash", **extra):
    e = {"hook_event_name": "PreToolUse", "tool_name": herramienta, "tool_input": {"command": comando}}
    if cwd is not None:
        e["cwd"] = cwd
    e.update(extra)
    return e


CONFIG_MINIMA = {"schema_version": 1, "repos": {}, "layers": {"doc": {"extensions": [".x"]}}}


def instancia(base, config=CONFIG_MINIMA):
    inst = base / "inst"
    inst.mkdir()
    texto = config if isinstance(config, str) else json.dumps(config)
    (inst / "workspace.config.json").write_text(texto, encoding="utf-8")
    return inst


def entorno_de(inst, **extra):
    return dict(ENTORNO, CLAUDE_PROJECT_DIR=str(inst), **extra)


def decision(comando, entorno=ENTORNO, cwd=None):
    return G.analizar(comando, cwd, entorno)[0]


class Mundo:
    def __init__(self, base, bandera, fuera):
        self.base = base
        self.equipo = base / "equipo"
        self.git_env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=str(base / "gitconfig"),
                            GIT_CONFIG_SYSTEM=str(base / "gitconfig-sistema"))
        propias = ("GIT_CONFIG_NOSYSTEM", "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM")
        for clave in [k for k in self.git_env if k.upper().startswith("GIT_") and k.upper() not in propias]:
            del self.git_env[clave]
        (base / "gitconfig").write_text("[user]\n\tname = prueba\n\temail = prueba@example.com\n", encoding="utf-8")
        self.repos = {"db": self.equipo / "db", "api": self.equipo / "web" / "api", "movil": self.equipo / "web" / "movil"}
        for ruta in self.repos.values():
            ruta.mkdir(parents=True)
            self.git(ruta, "init", "-q")
        self.git(self.repos["db"], "commit", "-q", "--allow-empty", "-m", "base")
        self.worktree = self.equipo / "worktrees" / "db--x"
        self.git(self.repos["db"], "worktree", "add", "-q", "-b", "x", str(self.worktree))
        self.fuera = None
        if fuera:
            self.fuera = base / "afuera" / "wt"
            self.git(self.repos["db"], "worktree", "add", "-q", "-b", "y", str(self.fuera))
        valor = {} if bandera is None else {"agent_readonly": bandera}
        config = {"schema_version": 1, "repos": {clave: dict(valor) for clave in self.repos},
                  "layers": {"doc": {"extensions": [".x"]}}}
        self.inst = instancia(base, config)
        local = {"repos": {clave: {"path": str(ruta)} for clave, ruta in self.repos.items()}}
        (self.inst / "workspace.local.json").write_text(json.dumps(local), encoding="utf-8")

    def git(self, carpeta, *args):
        subprocess.run(["git", "-C", str(carpeta), *args], check=True, capture_output=True, env=self.git_env, timeout=60)

    def protegidos(self):
        return G.Protegidos.de_instancia(self.inst)


@contextlib.contextmanager
def mundo(bandera=True, fuera=False):
    with carpeta() as base:
        yield Mundo(base, bandera, fuera)


ESPERADO = {"allow": None, "ask": "ask", "block": "block"}
SIN_PLEGAR = {
    "ruta sin distinguir mayúsculas": "block",
    "PUSH de MASTER con -C en mayúsculas": "allow",
    "Git Push a secas con el cwd en mayúsculas": "allow",
    "GIT SWITCH con la ruta de -C en minúsculas": "allow",
    "checkout con el cwd de un worktree en mayúsculas pregunta": "allow",
    "RM -RF del scratch en mayúsculas": "block",
    "REMOVE-ITEM del scratch en mayúsculas": "block",
}


def esperado_en_esta_plataforma(nombre, esperado):
    return esperado if PLIEGA else SIN_PLEGAR.get(nombre, esperado)


def test_casos_del_origen_con_la_decision_exacta():
    with mundo() as m:
        tabla = valores(m.equipo)
        if not PLIEGA:
            pares = (("AREA^", "AREA"), ("AREA~", "AREA"), ("SCRW^", "SCRW"), ("EQ^", "EQ"), ("EQ_", "EQ"), ("EQF^", "EQF"))
            assert all(tabla[a] != tabla[b] for a, b in pares), "control: cada variante cambia alguna mayúscula"
        prot = m.protegidos()
        assert prot.activa and prot.rota is None, prot.rota
        fallos = []
        for nombre, comando, cwd, esperado in CASOS:
            esperado = esperado_en_esta_plataforma(nombre, esperado)
            resultado, motivo = G.analizar(_r(comando, tabla), _cwd(cwd, tabla), ENTORNO, prot)
            if resultado != ESPERADO[esperado]:
                fallos.append("  %s: esperado %s, salio %s (%s)" % (nombre, esperado, resultado, motivo))
    conteo = {d: sum(1 for c in CASOS if c[3] == d) for d in ESPERADO}
    assert len(CASOS) == 370 and conteo == {"allow": 92, "ask": 190, "block": 88}, conteo
    assert set(SIN_PLEGAR) <= {c[0] for c in CASOS}, set(SIN_PLEGAR) - {c[0] for c in CASOS}
    assert not fallos, "%d fallos\n" % len(fallos) + "\n".join(fallos)


def test_sin_la_bandera_lo_que_preguntaba_pasa_y_la_capa_1_sigue():
    for bandera in (None, False):
        with mundo(bandera) as m:
            tabla = valores(m.equipo)
            prot = m.protegidos()
            assert not prot.activa and prot.rota is None, (bandera, prot.rota)
            for nombre, comando, cwd, esperado in CASOS:
                esperado = esperado_en_esta_plataforma(nombre, esperado)
                resultado = G.analizar(_r(comando, tabla), _cwd(cwd, tabla), ENTORNO, prot)[0]
                assert resultado == ("block" if esperado == "block" else None), (bandera, nombre, resultado)


BORDES_CAPA_1 = [
    ("GIT PUSH --FORCE-WITH-LEASE --FORCE ORIGIN X", "block"),
    ("git push --FORCE-WITH-LEASE origin +x", None),
    ("git push origin \\\n+main", "block"),
    ('git push "origin" +main', "block"),
    ("git push +origin main", None),
    ("git push -oci.flag origin main", None),
    ("git push origin -o +ci main", None),
    ("git push origin --push-option +ci main", None),
    ("git push --force-with-lease=x origin +y:x", None),
    ("git push --force-with-lease=x origin +x:y", "block"),
    ("git push --force-with-lease=main origin +main>log", None),
    ("echo 'git push --force origin main'", None),
    ("git push --force-with-lease origin x; echo --force", None),
    ("git log --h", None),
    ("git commit -F - <<'EOF'\npush --force\neof", None),
    ("python <<'EOF'\ngit push --force origin main\nEOF", "block"),
    ("rm -rf «SCR»/$X", "block"),
    ("rm -rf «SCR»/x/...", "block"),
    ("rm -rf «SCR»/.*", "block"),
    ("rm -rf «SCR»/x\\\"", "block"),
    ('rm -rf «SCR»/x "', "block"),
    ("sudo rm -rf «SCR»/x", "block"),
    ("sudo «SCR»/rm -rf «SCR»/x", "block"),
    ("rm /s/q", None),
    ("%rm -r c:/x", "block"),
    ("rm -rf 2>/dev/null", "block"),
    ("rm -rf «SCR»/x 2> /dev/null", None),
    ("test -d x || rm -rf «SCR»/x", None),
    ("Remove-Item -Path «SCRW»\\a -Recurse -Force", None),
    ("Remove-Item -Path:«SCRW»\\a -Recurse -Force", None),
    ("X=1 rm -r c:/x", "block"),
    ("{ rm -r c:/x; }", "block"),
    ("Remove-Item c:/x -Recu", "block"),
    ("rm --rec c:/x", "block"),
    ("Remove-Item c:/x -Recurse:$true", "block"),
]


def test_bordes_de_la_capa_1():
    tabla = valores(EQUIPO_SINTETICO)
    fallos = []
    for comando, esperado in BORDES_CAPA_1:
        resultado, motivo = G.analizar(_r(comando, tabla), None, ENTORNO)
        if resultado != esperado:
            fallos.append("  %r: esperado %s, salio %s (%s)" % (comando, esperado, resultado, motivo))
    assert not fallos, "\n" + "\n".join(fallos)


def test_cada_regla_da_su_propio_motivo():
    casos = [("git push -f origin main", "git push --force (si de verdad"),
             ("git push -uf origin main", "git push --force/-f (anula"),
             ("git push origin +main", 'git push con un refspec "+"'),
             ("git reset --hard", "git reset --hard descarta"),
             ("git clean -fd", "git clean -f borra"),
             ("rm -rf C:/fuera/x", "rm -rf fuera del scratch"),
             ("Remove-Item -Recurse -Force C:/fuera/x", "Remove-Item -Recurse -Force fuera del scratch"),
             ("rm -r C:/fuera/x", "borrado recursivo")]
    for comando, inicio in casos:
        resultado, motivo = G.analizar(_r(comando), None, ENTORNO)
        assert resultado == "block" and motivo.startswith(inicio), (comando, motivo)


def capa_2(m, comando, cwd=None, entorno=ENTORNO):
    return G.analizar(comando, None if cwd is None else str(cwd), entorno, m.protegidos())


def test_el_motivo_nombra_el_repo_y_la_bandera_sin_dominio():
    with mundo() as m:
        resultado, motivo = capa_2(m, "git commit -m x", m.repos["api"])
        assert resultado == "ask", (resultado, motivo)
        assert motivo.startswith("git commit en el repo «api», que el agente solo lee (repos.api.agent_readonly"), motivo
        assert motivo.endswith("requiere autorización puntual. Confirmar solo si es deliberado y autorizado."), motivo
        casos = [("git switch otra", "worktree add"), ("git checkout -- x.sql", "descarta trabajo sin commitear"),
                 ("git gc", "fuera de la lista de git de solo lectura"), ("git log --output=x", "esa opción escribe o ejecuta"),
                 ("git -c alias.x=!sh x", "opción global fuera de la lista"), ('echo \\"; git status', "comillas escapadas"),
                 ("$g push", "un comando en una variable"), ("Set-Alias g git; g push", "un alias hacia git"),
                 ("GIT_SSH_COMMAND=x git fetch", "una variable GIT_*")]
        for comando, parte in casos:
            resultado, motivo = capa_2(m, comando, m.repos["db"])
            assert resultado == "ask" and parte in motivo and "«db»" in motivo, (comando, motivo)
            assert capa_2(m, comando, PROYECTO) == (None, None), "fuera de un repo protegido, %s pasa" % comando


def test_un_worktree_registrado_cuenta_como_su_repo_y_una_copia_no():
    with mundo(fuera=True) as m:
        assert capa_2(m, "git commit -m x", m.fuera)[0] == "ask"
        assert "«db»" in capa_2(m, "git -C %s commit -m x" % fw(m.fuera), PROYECTO)[1]
        copia = m.base / "afuera" / "copia"
        copia.mkdir()
        m.git(copia, "init", "-q")
        assert capa_2(m, "git commit -m x", copia) == (None, None)
        assert capa_2(m, "git -C %s commit -m x" % fw(copia), m.repos["db"]) == (None, None)
        shutil.rmtree(m.repos["db"] / ".git" / "worktrees", onexc=_quitar)
        assert capa_2(m, "git commit -m x", m.fuera) == (None, None), "control: sin el registro de git, el worktree no se reconoce"


def test_protege_por_contencion_y_no_por_el_nombre():
    with mundo() as m:
        homonimo = m.base / "otro" / "equipo" / "db"
        homonimo.mkdir(parents=True)
        assert capa_2(m, "git commit -m x", homonimo) == (None, None)
        assert capa_2(m, "git -C %s push" % fw(homonimo), PROYECTO) == (None, None)
        mayusculas = capa_2(m, "git -C %s push" % str(m.repos["db"]).upper(), PROYECTO)[0]
        assert mayusculas == ("ask" if PLIEGA else None), "las mayúsculas cuentan donde el sistema no las distingue: %s" % mayusculas
        assert capa_2(m, "git -C %s push" % otra_grafia(m.repos["db"]), PROYECTO)[0] == "ask", otra_grafia(m.repos["db"])
        enlace = m.base / "enlace"
        if NT:
            r = subprocess.run(["cmd", "/c", "mklink", "/J", str(enlace), str(m.repos["db"])], capture_output=True)
            assert r.returncode == 0, r
        else:
            os.symlink(m.repos["db"], enlace, target_is_directory=True)
        try:
            assert capa_2(m, "git commit -m x", enlace)[0] == "ask"
            assert capa_2(m, "git -C %s commit -m x" % fw(enlace), PROYECTO)[0] == "ask"
        finally:
            (os.rmdir if NT else os.unlink)(enlace)


def test_en_macos_otras_mayusculas_o_la_forma_nfd_no_esconden_un_repo_protegido():
    with carpeta() as base:
        repo = base / "año" / "db"
        repo.mkdir(parents=True)
        nfd = fw(repo).replace("ñ", "n\u0303")
        config = {"repos": {"db": {"path": str(repo), "worktrees": [], "agent_readonly": True}}}
        with en_sistema("darwin"):
            prot = G.Protegidos(config)
            for variante in (nfd, fw(repo).upper()):
                assert G.analizar("git -C %s push" % variante, PROYECTO, ENTORNO, prot)[0] == "ask", variante
                assert G.analizar("git commit -m x", variante, ENTORNO, prot)[0] == "ask", variante
        with en_sistema("linux"):
            prot = G.Protegidos(config)
            assert G.analizar("git -C %s push" % nfd, PROYECTO, ENTORNO, prot) == (None, None), "fuera de macOS, NFD es otra carpeta"


def test_el_cwd_cuenta_solo_si_esta_dentro_de_un_repo_protegido():
    with mundo() as m:
        assert capa_2(m, "git commit -m x", m.repos["db"] / "sub")[0] == "ask"
        assert capa_2(m, "git commit -m x", m.equipo) == (None, None)
        assert capa_2(m, "git commit -m x", m.equipo / "web") == (None, None)


def test_una_mencion_que_contiene_un_repo_protegido_tambien_toca():
    with mundo() as m:
        eq = fw(m.equipo)
        for comando in ("cd %s; cd db; git commit -m x" % eq, "cd %s && git -C db commit -m x" % eq,
                        "cd %s/web && git -C api push" % eq, "Push-Location %s; git commit -m x" % bw(m.equipo)):
            assert capa_2(m, comando, PROYECTO)[0] == "ask", comando
        assert capa_2(m, "git add .", m.equipo)[0] == "ask", "costo aceptado en L53"
        assert capa_2(m, "cd %s/../otro && git commit -m x" % eq, PROYECTO) == (None, None)
        assert capa_2(m, "cd %s/web/apis && git commit -m x" % eq, PROYECTO) == (None, None)


def test_las_menciones_salen_del_token_del_igual_de_la_opcion_y_de_las_comas():
    with mundo() as m:
        db = fw(m.repos["db"])
        for comando in ("GIT_DIR=%s/.git git commit -m x" % db, "export R=%s; git commit -m x" % db, "x=y=%s; git commit -m x" % db,
                        "Set-Location -Path:%s; git commit -m x" % bw(m.repos["db"]), "ls a,%s; git commit -m x" % db,
                        "(cd %s) ; git commit -m x" % db, "$(cd %s); git commit -m x" % db, "echo x >%s/y; git commit -m x" % db,
                        "eval \"cd %s\"; git commit -m x" % db, "bash -c \"ls '%s'\"; git commit -m x" % db):
            assert capa_2(m, comando, PROYECTO)[0] == "ask", comando
        assert capa_2(m, 'git commit -m "docs: %s es de solo lectura"' % db, PROYECTO) == (None, None)
        assert capa_2(m, "git commit -m %s" % db, PROYECTO)[0] == "ask", "sin espacio, la mención cuenta (como el origen)"
        assert capa_2(m, "echo x/%s; git commit -m x" % db, PROYECTO) == (None, None), "una ruta pegada en medio no se ve"


def test_una_ruta_con_espacios_escapados_con_barra_tambien_toca():
    with carpeta() as base:
        repo = base / "con espacio" / "repo x"
        repo.mkdir(parents=True)
        prot = G.Protegidos({"repos": {"esp": {"path": str(repo), "worktrees": [], "agent_readonly": True}}})
        escapada = para_bash(repo).replace(" ", "\\ ")
        for comando in ("cd %s && git commit -m x" % escapada, "git -C %s commit -m x" % escapada,
                        "pushd %s; git commit -m x" % escapada, "cd %s/ && git add ." % escapada,
                        "git -C %s push" % fw(repo).replace(" ", "\\ ")):
            resultado, motivo = G.analizar(comando, PROYECTO, ENTORNO, prot)
            assert resultado == "ask" and "«esp»" in motivo, (comando, motivo)
        assert G.analizar("git -C %s status" % escapada, PROYECTO, ENTORNO, prot) == (None, None)
        for comando in ("git -C C:\\proyecto\\ commit -m x", "cd C:\\otra\\ carpeta && git commit -m x"):
            assert G.analizar(comando, PROYECTO, ENTORNO, prot) == (None, None), comando
        en_ps = "cd %s && git commit -m x" % escapada
        assert G.analizar(en_ps, PROYECTO, ENTORNO, prot, "PowerShell") == (None, None), "en PowerShell la barra no escapa"
        assert G.analizar('bash -c "%s"' % en_ps, PROYECTO, ENTORNO, prot, "PowerShell")[0] == "ask"
        assert G.analizar(en_ps, PROYECTO, ENTORNO, prot, "Bash")[0] == "ask"
        dentro = str(repo / "sub")
        for comando, herramienta in (("git --git-dir C:\\ blame f.sql", "PowerShell"),
                                     ("powershell -NoProfile -Command 'git -C C:\\ -C D:/x for-each-ref'", "Bash")):
            assert G.analizar(comando, dentro, ENTORNO, prot, herramienta) == (None, None), (comando, herramienta)
        assert G.analizar("git --git-dir C:\\ blame f.sql", dentro, ENTORNO, prot, "Bash")[0] == "ask", "bash lee C:\\ blame como una ruta"
        codigo, salida, _ = G.correr(evento(en_ps, cwd=PROYECTO, herramienta="PowerShell"), entorno=ENTORNO)
        assert (codigo, salida) == (0, ""), "sin instancia calla"
        igual = base / "a=b" / "repo"
        igual.mkdir(parents=True)
        prot = G.Protegidos({"repos": {"igual": {"path": str(igual), "worktrees": [], "agent_readonly": True}}})
        assert G.analizar("export R=%s; git commit -m x" % fw(igual), PROYECTO, ENTORNO, prot)[0] == "ask"


def test_la_forma_canonica_rapida_es_la_misma_que_la_de_config_loader():
    with mundo() as m:
        prot = m.protegidos()
        rutas_ = [m.repos["db"], m.repos["db"] / "no" / "existe.sql", m.worktree / "x", m.equipo, m.equipo / "nada" / "db",
                  m.base / "db.", m.repos["db"].parent / "db." / "x", m.base]
        enlace = m.base / "enlace"
        if NT:
            subprocess.run(["cmd", "/c", "mklink", "/J", str(enlace), str(m.repos["db"])], capture_output=True, check=True)
        else:
            os.symlink(m.repos["db"], enlace, target_is_directory=True)
            rutas_ += [otra_grafia(m.repos["db"]), otra_grafia(m.repos["db"] / "no" / "existe.sql")]
        rutas_ += [enlace, enlace / "sub" / "x.sql"]
        raiz, otra = ("C:/", "D:/x") if NT else ("/", "/x")
        try:
            for ruta in rutas_:
                r = G.rutas.ubicar(str(ruta), None)
                assert prot._canonica(r) == G.config_loader.canonica(r), (r, prot._canonica(r), G.config_loader.canonica(r))
                for arbol, _ in prot.arboles + [(G.config_loader.canonica(raiz), "raiz"), (G.config_loader.canonica(otra), "otra")]:
                    c = prot._canonica(r)
                    assert G._bajo(c, arbol) == G.config_loader._dentro(c, arbol), (c, arbol)
                    assert G._bajo(arbol, c) == G.config_loader._dentro(arbol, c), (arbol, c)
            hondo = G.rutas.ubicar(fw(m.base) + "/" + "/".join("s%d" % i for i in range(1500)), None)
            assert prot._canonica(hondo) == G.config_loader.canonica(hondo)
            if NT:
                assert prot._canonica("//Servidor/Recurso/X") == "\\\\servidor\\recurso\\x", "una ruta UNC no toca la red"
        finally:
            (os.rmdir if NT else os.unlink)(enlace)


def test_los_candidatos_de_un_token_largo_respetan_el_plazo():
    token = ",".join("k%d=C:/x%d" % (i, i) for i in range(600))
    assert len(G._candidatos(token[:4000])) < 2000
    G._LIMITE = 0.0
    try:
        G._candidatos(token)
    except G._SinTiempo:
        pass
    else:
        raise AssertionError("_candidatos no corta con el plazo vencido")
    finally:
        G._LIMITE = None


def test_un_separador_escapado_no_se_lee_como_la_raiz_de_la_unidad():
    with mundo() as m:
        for comando in ("find . -exec git stash pop \\;", 'echo \\"; git commit -m x', "git ls-files | xargs -I{} echo {}\\; git push"):
            assert capa_2(m, comando, PROYECTO) == (None, None), comando
        assert capa_2(m, "cd / && git -C %s commit -m x" % sin_raiz(m.repos["db"]), PROYECTO)[0] == "ask", "la raíz literal sí cuenta"


def test_variables_y_comodines_en_una_mencion_cortan_en_la_carpeta_conocida():
    with mundo() as m:
        entorno = dict(ENTORNO, REPOS=str(m.equipo))
        eq = fw(m.equipo)
        for comando in ("cd $REPOS/db && git commit -m x", "cd ${REPOS}/web/api && git push", "cd %REPOS%\\db && git commit -m x",
                        "cd $env:REPOS\\db; git commit -m x", "cd %s/$NADA && git commit -m x" % eq,
                        "cd %s/d* && git commit -m x" % eq, "cd %s/{db,web} && git commit -m x" % eq):
            assert capa_2(m, comando, PROYECTO, entorno)[0] == "ask", comando
        minusculas = capa_2(m, "cd $env:repos\\db; git commit -m x", PROYECTO, entorno)[0]
        assert minusculas == ("ask" if NT else None), "solo Windows ignora las mayúsculas del nombre de la variable"
        assert capa_2(m, "cd $NADA/db && git commit -m x", PROYECTO, entorno) == (None, None)
        assert capa_2(m, "cd $PWD/db && git commit -m x", m.equipo, entorno)[0] == "ask"
        assert capa_2(m, "cd $PWD/db && git commit -m x", PROYECTO, entorno) == (None, None)


def test_la_ruta_propia_absoluta_decide_sola_y_las_relativas_se_encadenan():
    with mundo() as m:
        db = m.repos["db"]
        assert capa_2(m, _r("git -C C:/proyecto commit -m x"), db) == (None, None)
        assert capa_2(m, _r("git --git-dir=C:/proyecto/.git commit -m x"), db) == (None, None)
        assert capa_2(m, "git -C %s -C db commit -m x" % fw(m.equipo), PROYECTO)[0] == "ask"
        assert capa_2(m, "git -C %s/web -C api --work-tree . commit -m x" % fw(m.equipo), PROYECTO)[0] == "ask"
        assert capa_2(m, _r("git -C C:/proyecto -C sub commit -m x"), db) == (None, None)
        assert capa_2(m, "git -C sub commit -m x", db)[0] == "ask", "relativa sin base: decide el ambiente"
        assert capa_2(m, "git -C C:x commit -m x", db)[0] == "ask", "relativa a la unidad: no es absoluta"
        assert capa_2(m, "git -C %s/$NADA commit -m x" % fw(m.equipo), PROYECTO)[0] == "ask"
        otra = fw(m.base / "otra")
        assert capa_2(m, "git -C %s -C ../equipo/db commit -m x" % otra, PROYECTO)[0] == "ask", "la cadena llega al repo"
        assert capa_2(m, "git -C %s -C ../afuera commit -m x" % otra, PROYECTO) == (None, None)
        if NT:
            for prefijo in ("\\\\?\\", "\\\\.\\"):
                assert capa_2(m, "git -C %s%s commit -m x" % (prefijo, bw(db)), PROYECTO)[0] == "ask", prefijo
        else:
            assert capa_2(m, "git -C %s commit -m x" % otra_grafia(db), PROYECTO)[0] == "ask", "con doble barra inicial"
            assert capa_2(m, "cd %s && git commit -m x" % otra_grafia(db), PROYECTO)[0] == "ask", "cd con doble barra inicial"
            assert capa_2(m, "git commit -m x", otra_grafia(db))[0] == "ask", "cwd con doble barra inicial"


def test_redirecciones_y_cierres_no_se_leen_como_el_subcomando():
    with mundo() as m:
        db = m.repos["db"]
        for comando in ("git 2> err.txt status", "git status 2>&1 > log.txt", "(git status)", "$(git log --oneline)",
                        "{ git diff; }", "echo `git status`"):
            assert capa_2(m, comando, db) == (None, None), comando
        assert capa_2(m, "(git commit -m x)", db)[0] == "ask"


def test_un_token_que_no_es_una_ruta_no_llega_a_realpath():
    with mundo() as m:
        prot = m.protegidos()
        vistas = []
        original, existe = G.config_loader.canonica, G._existe
        G.config_loader.canonica = lambda ruta: vistas.append(ruta) or original(ruta)
        G._existe = lambda ruta: vistas.append(ruta) or existe(ruta)
        try:
            for comando in ('echo "a\x00b"; git commit -m x', 'echo "a\nb c"; git commit -m x',
                            "echo " + "x/" * 2100 + "; git commit -m x"):
                assert G.analizar(comando, PROYECTO, ENTORNO, prot) == (None, None), comando[:40]
        finally:
            G.config_loader.canonica, G._existe = original, existe
        assert vistas and not [r for r in vistas if "\x00" in r or "\n" in r or len(r) > G.MAX_RUTA], [r[:60] for r in vistas]


def test_la_compuerta_tambien_se_abre_por_una_mencion():
    with mundo() as m:
        db = fw(m.repos["db"])
        for comando in ("cd %s && GIT_SSH_COMMAND=x git fetch" % db, 'cd %s; echo \\"; git status' % db):
            assert capa_2(m, comando, PROYECTO)[0] == "ask", comando
            assert capa_2(m, comando.replace(db, "C:/proyecto/sub"), PROYECTO) == (None, None), comando


def test_un_heredoc_a_un_shell_hace_codigo_tambien_al_otro_heredoc_como_el_origen():
    with mundo() as m:
        db = fw(m.repos["db"])
        commit = "git commit -F - <<'EOF'\nnota %s git push\nEOF\n" % db
        assert capa_2(m, commit + "ls", PROYECTO) == (None, None)
        assert capa_2(m, commit + "cat <<'X' | bash\necho hola\nX", PROYECTO)[0] == "ask"


def test_cada_subcomando_de_git_escribe_de_writer_guard_pregunta():
    spec = importlib.util.spec_from_file_location("writer_guard_escribe", AQUI / "writer_guard.py")
    w = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(w)
    assert len(w.GIT_ESCRIBE) == 20
    with mundo() as m:
        db = m.repos["db"]
        for sub in sorted(w.GIT_ESCRIBE):
            assert capa_2(m, "git %s" % sub, db)[0] == "ask", sub
            assert capa_2(m, "git -C %s %s x" % (fw(db), sub), PROYECTO)[0] == "ask", sub
        assert capa_2(m, "git branch -d x", db)[0] == "ask"


def test_pregunta_con_json_limpio_en_stdout_y_exit_0():
    with mundo() as m:
        for herramienta in ("Bash", "PowerShell"):
            codigo, salida, error = G.correr(evento("git commit -m x", cwd=str(m.repos["db"]), herramienta=herramienta),
                                             entorno=entorno_de(m.inst))
            assert (codigo, error) == (0, b"") and salida.endswith("\n") and salida.isascii(), (codigo, salida, error)
            datos = json.loads(salida)
            hso = datos["hookSpecificOutput"]
            assert set(datos) == {"hookSpecificOutput"} and set(hso) == {"hookEventName", "permissionDecision", "permissionDecisionReason"}, datos
            assert (hso["hookEventName"], hso["permissionDecision"]) == ("PreToolUse", "ask"), hso
            assert hso["permissionDecisionReason"].startswith("guard-comandos pregunta antes de correr el comando: git commit en el repo «db»"), hso
        assert G.correr(evento("git push --force origin x", cwd=str(m.repos["db"])), entorno=entorno_de(m.inst))[0] == 2
        assert G.correr(evento("git status", cwd=str(m.repos["db"])), entorno=entorno_de(m.inst)) == (0, "", b"")


def _razon(resultado):
    return json.loads(resultado[1])["hookSpecificOutput"]["permissionDecisionReason"] if resultado[1] else None


def test_con_la_config_rota_todo_git_que_no_es_de_lectura_pregunta_en_cualquier_repo():
    with carpeta() as base:
        inst = instancia(base, {"schema_version": 1, "repos": {"db": {"agent_readonly": True}}, "layers": {"doc": {"extensions": [".x"]}}})
        prot = G.Protegidos.de_instancia(inst)
        assert prot.activa and "db" in prot.rota, prot.rota
        for comando in ("git commit -m x", "git -C C:/proyecto push", "git add ."):
            resultado = G.correr(evento(comando, cwd=PROYECTO), entorno=entorno_de(inst))
            razon = _razon(resultado)
            assert resultado[0] == 0 and razon and "configuración de la instancia rota" in razon and "falta la ruta del repo 'db'" in razon, (comando, resultado)
        for comando in ("git status", "git log --oneline", "ls"):
            assert G.correr(evento(comando, cwd=PROYECTO), entorno=entorno_de(inst)) == (0, "", b""), comando
        assert G.correr(evento("git reset --hard", cwd=PROYECTO), entorno=entorno_de(inst))[0] == 2
    with mundo("true") as m:
        prot = m.protegidos()
        assert "agent_readonly" in prot.rota, prot.rota
        assert "agent_readonly" in _razon(G.correr(evento("git commit -m x", cwd=PROYECTO), entorno=entorno_de(m.inst)))


def test_una_config_que_revienta_al_leerse_cuenta_como_rota():
    with carpeta() as base:
        inst = instancia(base, {"schema_version": 1, "repos": {"db": "texto"}, "layers": {"doc": {"extensions": [".x"]}}})
        (inst / "workspace.local.json").write_text(json.dumps({"repos": {"db": {"path": str(base)}}}), encoding="utf-8")
        try:
            config_loader.cargar(inst)
        except config_loader.ConfigRota:
            raise AssertionError("control: esta config tiene que reventar con algo que no es ConfigRota")
        except Exception:
            pass
        prot = G.Protegidos.de_instancia(inst)
        assert prot.activa and prot.rota, prot.rota
        assert "configuración de la instancia rota" in _razon(G.correr(evento("git commit -m x"), entorno=entorno_de(inst)))


def test_el_hook_lee_el_escape_segun_la_herramienta_del_evento():
    with mundo() as m:
        comando = "git --git-dir C:\\ blame f.sql"
        assert G.correr(evento(comando, cwd=str(m.repos["db"]), herramienta="PowerShell"), entorno=entorno_de(m.inst)) == (0, "", b"")
        assert G.correr(evento(comando, cwd=str(m.repos["db"]), herramienta="Bash"), entorno=entorno_de(m.inst))[1], "Bash lee C:\\ blame"


def test_con_el_plazo_vencido_pregunta_si_hay_repos_marcados():
    with mundo() as m:
        resultado = G.correr(evento("git status", cwd=str(m.base)), entorno=entorno_de(m.inst), plazo=-1)
        assert resultado[0] == 0 and "no terminó dentro del plazo" in _razon(resultado), resultado
        assert G.correr(evento("git status", cwd=str(m.repos["db"])), entorno=entorno_de(m.inst), plazo=8) == (0, "", b"")
    with mundo(False) as m:
        assert G.correr(evento("git commit -m x", cwd=str(m.repos["db"])), entorno=entorno_de(m.inst), plazo=-1) == (0, "", b"")
    with carpeta() as base:
        inst = instancia(base, "{ rota")
        razon = _razon(G.correr(evento("ls"), entorno=entorno_de(inst), plazo=-1))
        assert "no terminó dentro del plazo" in razon and "no se puede leer como JSON" in razon, razon


def test_una_falla_interna_pregunta_si_la_capa_2_esta_activa():
    original = G._invocacion

    def revienta(*_a, **_k):
        raise RuntimeError("falla sembrada")

    G._invocacion = revienta
    try:
        with mundo() as m:
            resultado = G.correr(evento("git status", cwd=str(m.repos["db"])), entorno=entorno_de(m.inst))
            razon = _razon(resultado)
            assert resultado[0] == 0 and "error interno" in razon and "falla sembrada" in razon, resultado
        with mundo(None) as m:
            assert G.correr(evento("git status", cwd=str(m.repos["db"])), entorno=entorno_de(m.inst)) == (0, "", b"")
    finally:
        G._invocacion = original
    for nombre in ("Segmentos", "_capa_1"):
        original = getattr(G, nombre)
        setattr(G, nombre, revienta)
        try:
            with mundo() as m:
                razon = _razon(G.correr(evento("git status", cwd=str(m.repos["db"])), entorno=entorno_de(m.inst)))
                assert razon and "falla sembrada" in razon, (nombre, razon)
            with mundo(None) as m:
                assert G.correr(evento("git status", cwd=str(m.repos["db"])), entorno=entorno_de(m.inst)) == (0, "", b""), nombre
            with carpeta() as base:
                inst = instancia(base, "{ rota")
                razon = _razon(G.correr(evento("git status"), entorno=entorno_de(inst)))
                assert "falla sembrada" in razon and "no se puede leer como JSON" in razon, (nombre, razon)
        finally:
            setattr(G, nombre, original)


def test_el_hook_real_pregunta_como_proceso():
    with mundo() as m:
        entorno = dict(os.environ, **entorno_de(m.inst))
        entorno.pop("PYTHONDONTWRITEBYTECODE", None)
        datos = json.dumps(evento("git commit -m x", cwd=str(m.repos["db"]))).encode("utf-8")
        r = subprocess.run([sys.executable, str(_RUTA), "--plazo", "8"], input=datos, capture_output=True, env=entorno,
                           cwd=str(m.base), timeout=60)
        assert r.returncode == 0 and r.stderr == b"", r
        assert json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"] == "ask", r.stdout


def test_sin_instancia_calla_aunque_sea_un_push_forzado():
    with carpeta() as base:
        suelta = base / "suelta"
        suelta.mkdir()
        assert G.correr(evento("git push --force origin main", cwd=str(suelta)), entorno=dict(ENTORNO)) == (0, "", b"")
        inst = instancia(base)
        assert config_loader.estado(inst).tipo == "ok"
        assert G.correr(evento("git push --force origin main", cwd=str(suelta)), entorno=entorno_de(inst))[0] == 2


def test_con_la_config_rota_la_capa_1_sigue_bloqueando():
    with carpeta() as base:
        inst = instancia(base, "{ esto no es json")
        assert config_loader.estado(inst).tipo == "rota"
        assert G.correr(evento("git reset --hard HEAD~1"), entorno=entorno_de(inst))[0] == 2
        assert G.correr(evento("git status"), entorno=entorno_de(inst)) == (0, "", b"")


def test_bloquea_con_exit_2_y_el_mensaje_en_bytes_utf8():
    with carpeta() as base:
        inst = instancia(base)
        for herramienta in ("Bash", "PowerShell"):
            codigo, salida, error = G.correr(evento("git push --force origin main", herramienta=herramienta), entorno=entorno_de(inst))
            assert (codigo, salida) == (2, ""), (herramienta, codigo, salida)
            texto = error.decode("utf-8")
            assert texto.startswith("guard-comandos bloqueó el comando: git push --force"), texto
            assert "a mano" in texto and texto.endswith("\n"), texto


def test_el_mensaje_de_un_borrado_nombra_el_scratch_del_entorno():
    with carpeta() as base:
        inst = instancia(base)
        codigo, _, error = G.correr(evento(_r("rm -rf C:/fuera/x")), entorno=entorno_de(inst))
        assert codigo == 2
        assert "rm -rf fuera del scratch" in error.decode("utf-8"), error
        assert "dentro de %s)" % RAIZ_SCRATCH in error.decode("utf-8"), error


def test_lo_que_no_bloquea_pasa_en_silencio():
    with carpeta() as base:
        inst = instancia(base)
        for comando in ("git status", "rm -rf %s/tmp" % SCR, "git push origin main", "ls -la"):
            assert G.correr(evento(comando), entorno=entorno_de(inst)) == (0, "", b""), comando


def test_una_entrada_rota_o_ajena_calla():
    with carpeta() as base:
        inst = instancia(base)
        e = entorno_de(inst)
        for malo in (b"no es json", b"", b"[]", {"tool_input": "git push --force"}, {"tool_input": {"command": "  "}},
                     {"tool_input": {"command": 7}}, evento("git push --force", hook_event_name="PostToolUse")):
            assert G.correr(malo, entorno=e) == (0, "", b""), malo
        crudo = json.dumps(evento("git push --force origin main")).encode("utf-8")
        assert G.correr(crudo, entorno=e)[0] == 2
        assert G.correr(b"\xef\xbb\xbf" + crudo, entorno=e)[0] == 2


def test_sin_hook_event_name_o_con_cualquier_herramienta_el_comando_se_analiza():
    with carpeta() as base:
        e = entorno_de(instancia(base))
        empuje = evento("git push --force origin main")
        esperado = G.correr(empuje, entorno=e)
        assert esperado[0] == 2, "control positivo"
        sin_nombre = {k: v for k, v in empuje.items() if k != "hook_event_name"}
        assert G.correr(sin_nombre, entorno=e) == esperado, "sin hook_event_name cuenta como PreToolUse"
        assert G.correr(json.dumps(sin_nombre).encode("utf-8"), entorno=e) == esperado
        assert G.correr(dict(sin_nombre, hook_event_name=None), entorno=e) == (0, "", b""), "solo cuenta la clave ausente"
        for herramienta in ("Edit", "Grep", None, 7):
            assert G.correr(evento("git push --force origin main", herramienta=herramienta), entorno=e) == esperado, herramienta
        assert G.correr({k: v for k, v in empuje.items() if k != "tool_name"}, entorno=e) == esperado


def test_con_el_plazo_vencido_calla_y_el_limite_no_queda_para_la_siguiente():
    with carpeta() as base:
        inst = instancia(base)
        assert G.correr(evento("git push --force origin main"), entorno=entorno_de(inst), plazo=-1) == (0, "", b"")
        assert G.analizar("git push --force origin main", None, ENTORNO)[0] == "block"
        assert G.correr(evento("git push --force origin main"), entorno=entorno_de(inst), plazo=8)[0] == 2


@contextlib.contextmanager
def en_sistema(nombre, uid=501):
    from odd_ws import comun, rutas
    previo = rutas.PLATAFORMA, comun._uid
    rutas.PLATAFORMA, comun._uid = nombre, (lambda: uid)
    try:
        yield
    finally:
        rutas.PLATAFORMA, comun._uid = previo


def test_el_scratch_sale_del_temporal_del_entorno():
    if not NT:
        en_tmpdir, en_tmp = ("rm -rf %s/claude-%d/x" % (base, os.getuid()) for base in ("/datos/beto/tmp", "/tmp"))
        propio = {"TMPDIR": "/datos/beto/tmp"}
        if sys.platform == "darwin":
            assert decision(en_tmp, propio) is None, "en macOS el scratch vive en /tmp aunque haya TMPDIR"
            assert decision(en_tmpdir, propio) == "block"
        else:
            assert decision(en_tmpdir, propio) is None
            assert decision(en_tmp, propio) == "block"
        assert decision(en_tmp, {}) is None
        return
    otro = {"TEMP": "C:\\Users\\beto\\AppData\\Local\\Temp", "SYSTEMROOT": "C:\\Windows"}
    assert decision("rm -rf C:/Users/beto/AppData/Local/Temp/claude/x", otro) is None
    assert decision("rm -rf C:/Users/ana/AppData/Local/Temp/claude/x", otro) == "block"
    solo_tmp = {"TMP": "C:\\Users\\beto\\AppData\\Local\\Temp", "SYSTEMROOT": "C:\\Windows"}
    assert decision("rm -rf C:/Users/beto/AppData/Local/Temp/claude/x", solo_tmp) is None
    assert decision("rm -rf C:/Users/beto/AppData/Local/Temp/claude/x", {"temp": "C:\\Users\\beto\\AppData\\Local\\Temp"}) is None
    sistema = {"SYSTEMROOT": "C:\\Windows"}
    assert decision("rm -rf C:/Windows/temp/claude/x", sistema) is None
    assert decision("rm -rf C:/Windows/temp/claude/x", {}) == "block"


def test_en_posix_el_scratch_es_el_de_claude_code_y_una_barra_no_es_una_unidad():
    with en_sistema("linux", uid=1000):
        assert decision("rm -rf /datos/tmp/claude-1000/x", {"TMPDIR": "/datos/tmp"}) is None
        assert decision("rm -rf /tmp/claude-1000/x", {"TMPDIR": "/datos/tmp"}) == "block"
        assert decision("rm -rf /tmp/claude-1000/x", {}) is None
        assert decision("Remove-Item -Recurse -Force \\tmp\\claude-1000\\x", {}) is None
        assert decision("rm -rf ~/claude-1000/x", {"HOME": "/tmp"}) is None
        for otro in ("/tmp/claude-1001/x", "/tmp/claude/x", "/tmp/claude-1000", "/tmp/claude-1000/x/..", "tmp/claude-1000/x"):
            assert decision("rm -rf " + otro, {}) == "block", otro
        assert decision("rm -rf /c/t/claude-1000/x", {"TMPDIR": "c:/t"}) == "block", "en POSIX, /c/ no es la unidad C:"
        assert decision("rm -rf /datos/tmp/claude-10000/x", {"TMPDIR": "/datos/tmp"}) == "block", "un hermano con el mismo prefijo"
    with en_sistema("darwin", uid=501):
        assert decision("rm -rf /tmp/claude-501/x", {"TMPDIR": "/var/folders/x/T/"}) is None
        assert decision("rm -rf /var/folders/x/T/claude-501/x", {"TMPDIR": "/var/folders/x/T/"}) == "block"


def test_en_posix_una_barra_invertida_de_bash_no_cuenta_como_scratch():
    for sistema, uid in (("linux", 1000), ("darwin", 501)):
        raiz = "/tmp/claude-%d" % uid
        with en_sistema(sistema, uid=uid):
            for destino in (raiz + "/.\\./.\\./fuera/x", raiz + "/.\\./.\\./fuera"):
                for comando in ("rm -rf ", "rm -r "):
                    assert decision(comando + destino, {}) == "block", "bash lee .\\. como ..: %s %s" % (sistema, comando + destino)
            assert decision("Remove-Item -Recurse -Force %s\\x" % bw(raiz), {}) is None, "en un cmdlet de PowerShell la barra separa"
            assert G.analizar("rm -rf %s/x\\y" % raiz, None, {}, None, "PowerShell")[0] is None, "PowerShell no escapa con la barra"


def test_en_bash_una_barra_invertida_sin_comillas_no_cuenta_como_scratch_tampoco_en_windows():
    for destino in (SCR + "/.\\./.\\./fuera/x", SCR + "/.\\./.\\./fuera", bw(SCR) + "\\x"):
        for comando in ("rm -rf ", "rm -r ", "rm -r -Path "):
            for herramienta in (None, "Bash"):
                resultado = G.analizar(comando + destino, None, ENTORNO, None, herramienta)[0]
                assert resultado == "block", "bash lee \\. como . y C:\\x como C:x: %s (%s)" % (comando + destino, herramienta)
    for comando in ("rm -rf %s/.\\./.\\./x" % SCR, "Remove-Item -Recurse -Force %s/.\\./.\\./x" % SCR):
        assert G.analizar(comando, None, ENTORNO, None, "PowerShell")[0] is None, "en PowerShell la barra separa: %s" % comando


def test_en_windows_la_barra_invertida_de_bash_entre_comillas_sigue_separando():
    esperado = None if NT else "block"
    for destino in ('"%s\\x"' % bw(SCR), "'%s\\x'" % bw(SCR), '"%s/.\\./.\\./x"' % SCR, '"%s\\\\x"' % bw(SCR)):
        for herramienta in (None, "Bash"):
            resultado = G.analizar("rm -rf " + destino, None, ENTORNO, None, herramienta)[0]
            assert resultado == esperado, "entre comillas bash deja la barra literal: %s (%s): %s" % (destino, herramienta, resultado)


def test_los_borrados_dentro_del_scratch_con_barras_normales_siguen_pasando():
    for destino in (SCR + "/tmp", '"%s/tmp dir"' % SCR, "'%s/tmp'" % SCR, SCR + "/x/../y", "%s/a %s/b" % (SCR, SCR)):
        for comando in ("rm -rf ", "rm -r "):
            for herramienta in (None, "Bash", "PowerShell"):
                assert G.analizar(comando + destino, None, ENTORNO, None, herramienta)[0] is None, (comando + destino, herramienta)


def test_en_posix_un_enlace_del_scratch_seguido_de_dos_puntos_no_se_lee_como_texto():
    if NT:
        print("      (en Windows la ruta se normaliza antes de resolver los enlaces: lo prueba el CI de POSIX)")
        return
    with carpeta() as base:
        repo = base / "repo"
        (repo / "sub").mkdir(parents=True)
        uid = 900000000 + os.getpid()
        for sistema, temporal, entorno in (("linux", base / "tmp", {"TMPDIR": str(base / "tmp")}), ("darwin", Path("/tmp"), {})):
            scratch = temporal / ("claude-%d" % uid)
            try:
                scratch.mkdir(parents=True)
            except FileExistsError:
                print("      (%s ya existe: se omite %s)" % (scratch, sistema))
                continue
            enlace = scratch / "jdb"
            try:
                os.symlink(repo / "sub", enlace, target_is_directory=True)
                with en_sistema(sistema, uid=uid):
                    for comando in ("rm -rf %s/jdb/../x", "rm -r %s/jdb/../x", "Remove-Item -Recurse -Force %s/jdb/../x"):
                        assert decision(comando % fw(scratch), entorno) == "block", (sistema, comando)
                    assert decision("rm -rf %s/x/../y" % fw(scratch), entorno) is None, "sin enlace, x/../y sigue en el scratch"
            finally:
                if enlace.is_symlink():
                    os.unlink(enlace)
                os.rmdir(scratch)


@contextlib.contextmanager
def posix_emulado(enlaces, carpetas):
    import posixpath
    from odd_ws import comun, rutas

    def real(ruta, saltos=0):
        if saltos > 40:
            raise OSError("demasiados enlaces: %s" % ruta)
        actual = "/"
        for parte in ruta.split("/"):
            camino = posixpath.join(actual, parte)
            if parte in ("", "."):
                continue
            if parte == "..":
                actual = posixpath.dirname(actual)
            elif camino in enlaces:
                actual = real(enlaces[camino], saltos + 1)
            elif camino in carpetas:
                actual = camino
            else:
                raise FileNotFoundError(ruta)
        return actual

    def lstat(ruta):
        padre, nombre = posixpath.split(os.fspath(ruta))
        final = posixpath.join(real(padre), nombre) if nombre not in ("", ".", "..") else real(os.fspath(ruta))
        if final in enlaces:
            return os.stat_result((stat.S_IFLNK | 0o777,) + (0,) * 9)
        if final in carpetas:
            return os.stat_result((stat.S_IFDIR | 0o755,) + (0,) * 9)
        raise FileNotFoundError(ruta)

    previo = os.name, os.sep, os.path, os.lstat, os.readlink, rutas.PLATAFORMA, comun._uid
    os.name, os.sep, os.path, os.lstat, os.readlink = "posix", "/", posixpath, lstat, (lambda ruta: enlaces[os.fspath(ruta)])
    rutas.PLATAFORMA, comun._uid = "linux", (lambda: 1000)
    try:
        yield
    finally:
        os.name, os.sep, os.path, os.lstat, os.readlink, rutas.PLATAFORMA, comun._uid = previo


SONDAS_DOS_PUNTOS = [
    ("git -C /home/u/afuera/l/.. push", "ask"),
    ("git -C /home/u/noexiste/../equipo/db push", "ask"),
    ("mkdir /home/u/n && git -C /home/u/n/../equipo/db push", "ask"),
    ("mkdir /home/u/n && git -C /home/u/n/../afuera/l push", "ask"),
    ("git -C /home/u/equipo/db/afuera/.. push", None),
    ("git -C /home/u/hecha/../equipo/db/no/.. push", "ask"),
    ("mkdir /home/u/n && cd /home/u/n/./../afuera/l/.. && git commit -m x", "ask"),
    ("git -C /home/u/hecha/../noexiste/./x status", None),
    ("cd /home/u/afuera/x/.. && git -C /home/u/afuera/x/../l push", "ask"),
]


def test_en_posix_la_capa_2_resuelve_los_dos_puntos_como_el_kernel():
    enlaces = {"/home/u/afuera/l": "/home/u/equipo/db/sub", "/home/u/equipo/db/afuera": "/srv/otra"}
    carpetas = {"/home", "/home/u", "/home/u/afuera", "/home/u/hecha", "/home/u/equipo", "/home/u/equipo/db",
                "/home/u/equipo/db/sub", "/srv", "/srv/otra"}
    fallos = []
    with posix_emulado(enlaces, carpetas):
        prot = G.Protegidos({"repos": {"db": {"path": "/home/u/equipo/db", "worktrees": [], "agent_readonly": True}}})
        for comando, esperado in SONDAS_DOS_PUNTOS:
            resultado, motivo = G.analizar(comando, "/srv/otra", {}, prot)
            if resultado != esperado:
                fallos.append("  %s: esperado %s, salio %s (%s)" % (comando, esperado, resultado, motivo))
            for token in comando.split():
                r = G.rutas.ubicar(token, None) if token.startswith("/") else None
                if r is not None and prot._canonica(r) != G.config_loader.canonica(r):
                    fallos.append("  %s: rápida %s, canonica %s" % (r, prot._canonica(r), G.config_loader.canonica(r)))
    assert not fallos, "\n" + "\n".join(fallos)


def test_en_posix_un_enlace_real_seguido_de_dos_puntos_en_la_capa_2():
    if NT:
        print("      (en Windows el .. se resuelve como texto antes de seguir el enlace: lo prueba el CI de POSIX)")
        return
    with carpeta() as base:
        repo, afuera, otra = base / "equipo" / "db", base / "afuera", base / "otra"
        for c in (repo / "sub", afuera, otra):
            c.mkdir(parents=True)
        os.symlink(repo / "sub", afuera / "l", target_is_directory=True)
        os.symlink(otra, repo / "afuera", target_is_directory=True)
        prot = G.Protegidos({"repos": {"db": {"path": str(repo), "worktrees": [], "agent_readonly": True}}})
        b = fw(base)
        for comando, esperado in (("git -C %s/afuera/l/.. push" % b, "ask"), ("git -C %s/noexiste/../equipo/db push" % b, "ask"),
                                  ("mkdir %s/n && git -C %s/n/../equipo/db push" % (b, b), "ask"),
                                  ("mkdir %s/n && git -C %s/n/../afuera/l push" % (b, b), "ask"),
                                  ("git -C %s/equipo/db/afuera/.. push" % b, None)):
            assert G.analizar(comando, str(otra), {}, prot)[0] == esperado, comando


def test_el_scratch_de_otro_usuario_o_de_otra_unidad_bloquea():
    if not NT:
        assert decision("rm -rf %s/x" % RAIZ_SCRATCH) is None
        for otro in ("/tmp/claude-%d/x" % (os.getuid() + 1), "/tmp/claude/x", "/otra/tmp/claude-%d/x" % os.getuid()):
            assert decision("rm -rf " + otro) == "block", otro
        return
    assert decision("rm -rf C:/Users/ana/AppData/Local/Temp/claude/x") is None
    assert decision("rm -rf C:/Users/beto/AppData/Local/Temp/claude/x") == "block"
    assert decision("rm -rf D:/Users/ana/AppData/Local/Temp/claude/x") == "block"
    assert decision("rm -rf /d/Users/ana/AppData/Local/Temp/claude/x") == "block"
    assert decision("Remove-Item -Recurse -Force C:\\Users\\beto\\AppData\\Local\\Temp\\claude\\x") == "block"


def test_la_raiz_del_scratch_no_se_puede_borrar():
    for destino in (RAIZ_SCRATCH, RAIZ_SCRATCH + "/", RAIZ_SCRATCH + "/.", RAIZ_SCRATCH + "/x/..", RAIZ_SCRATCH.rsplit("/", 1)[0]):
        assert decision("rm -rf " + destino) == "block", destino
    assert decision("rm -rf %s/x/../y" % RAIZ_SCRATCH) is None


def test_la_tilde_usa_la_carpeta_del_usuario_del_entorno():
    if NT:
        casa, sufijo = ENTORNO, "AppData/Local/Temp/claude"
    else:
        casa, sufijo = {"HOME": "/tmp"}, "claude-%d" % os.getuid()
    assert decision("rm -rf ~/%s/x" % sufijo, casa) is None
    assert decision("rm -rf ~/x", casa) == "block"
    assert decision("rm -rf ~beto/%s/x" % sufijo, casa) == "block"
    sin_casa = {k: v for k, v in casa.items() if k not in ("HOME", "USERPROFILE")}
    assert decision("rm -rf ~/%s/x" % sufijo, sin_casa) == "block"
    if NT:
        assert decision("rm -rf ~/AppData/Local/Temp/claude/x", dict(ENTORNO, HOME="/c/Users/ana")) is None


def test_un_enlace_del_scratch_hacia_afuera_bloquea():
    with carpeta() as base:
        temp = base / "tmp"
        nombre = "claude" if NT else "claude-%d" % os.getuid()
        (temp / nombre / "k").mkdir(parents=True)
        fuera = base / "fuera"
        fuera.mkdir()
        enlace = temp / nombre / "j"
        if NT:
            r = subprocess.run(["cmd", "/c", "mklink", "/J", str(enlace), str(fuera)], capture_output=True)
            assert r.returncode == 0 and enlace.exists(), r
            entorno, sistema = {"TEMP": str(temp), "SYSTEMROOT": "C:\\Windows"}, contextlib.nullcontext()
        else:
            os.symlink(fuera, enlace, target_is_directory=True)
            entorno, sistema = {"TMPDIR": str(temp)}, en_sistema("linux", uid=os.getuid())
        with sistema:
            assert decision("rm -rf %s/k/x" % fw(temp / nombre), entorno) is None
            assert decision("rm -rf %s/j/x" % fw(temp / nombre), entorno) == "block"
            assert decision("Remove-Item -Recurse -Force %s\\j" % bw(temp / nombre), entorno) == "block"


def test_el_hook_real_como_proceso():
    with carpeta() as base:
        inst = instancia(base)
        entorno = dict(os.environ, **entorno_de(inst))
        entorno.pop("PYTHONDONTWRITEBYTECODE", None)

        def correr_hook(datos):
            return subprocess.run([sys.executable, str(_RUTA), "--plazo", "8"], input=datos, capture_output=True, env=entorno,
                                  cwd=str(base), timeout=60)

        r = correr_hook(json.dumps(evento("git push --force origin main")).encode("utf-8"))
        assert r.returncode == 2 and r.stdout == b"", r
        assert r.stderr.decode("utf-8").startswith("guard-comandos bloqueó el comando"), r.stderr
        r = correr_hook(json.dumps(evento("git status")).encode("utf-8"))
        assert (r.returncode, r.stdout, r.stderr) == (0, b"", b""), r
        r = correr_hook(b"\x00 basura")
        assert (r.returncode, r.stdout, r.stderr) == (0, b"", b""), r


def test_los_dos_guards_resuelven_las_rutas_con_odd_ws_rutas():
    from odd_ws import rutas
    spec = importlib.util.spec_from_file_location("writer_guard_atado", AQUI / "writer_guard.py")
    w = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(w)
    assert G.rutas is rutas
    for nombre in ("normalizar", "es_relativa", "caso", "unidad", "ubicar", "absoluta", "antes_del_comodin"):
        assert getattr(w, "_" + nombre) is getattr(rutas, nombre), nombre
    assert not any(hasattr(w, n) for n in ("DRIVE", "UNIDAD_ABSOLUTA", "UNIDAD_SOLA", "GIT_BASH_DRIVE", "COMODIN", "VARIABLE_RE"))


def _hooks_del_plugin():
    datos = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    for evento_, grupos in datos["hooks"].items():
        for grupo in grupos:
            for h in grupo["hooks"]:
                yield evento_, grupo.get("matcher") or "", h


def test_esta_cableado_en_pre_tool_use_de_bash_y_powershell_con_8_s():
    cableados = [(e, m, h) for e, m, h in _hooks_del_plugin() if h["args"][0] == "${CLAUDE_PLUGIN_ROOT}/scripts/guard_comandos.py"]
    assert len(cableados) == 1, cableados
    evento_, matcher, h = cableados[0]
    assert evento_ == "PreToolUse" and set(matcher.split("|")) == {"Bash", "PowerShell"}, (evento_, matcher)
    assert h["type"] == "command" and h["command"] == "python3" and h.get("onFailure") == "block", h
    assert (h["timeout"], plazo_de(h["args"][1:])) == (10, 8), h


@contextlib.contextmanager
def plataforma(nombre):
    from odd_ws.hosts import codex
    previo = codex.SISTEMA
    codex.SISTEMA = nombre
    try:
        yield
    finally:
        codex.SISTEMA = previo


def parche_codex(*lineas):
    return "\n".join(("*** Begin Patch",) + lineas + ("*** End Patch",)) + "\n"


def instancia_protegida(base):
    repo = base / "equipo" / "db"
    repo.mkdir(parents=True)
    inst = instancia(base, {"schema_version": 1, "repos": {"db": {"agent_readonly": True}}, "layers": {"doc": {"extensions": [".x"]}}})
    (inst / "workspace.local.json").write_text(json.dumps({"repos": {"db": {"path": str(repo)}}}), encoding="utf-8")
    return inst, repo


def test_codex_un_parche_de_dos_archivos_no_es_un_comando_de_shell():
    with carpeta() as base:
        inst = instancia(base)
        texto = parche_codex("*** Add File: a.sh", "+git push --force origin main", "*** Update File: b.sh", "@@",
                             "+git reset --hard HEAD~1")
        parche = {"hook_event_name": "PreToolUse", "tool_name": "apply_patch", "tool_input": {"command": texto}}
        assert G.correr(parche, entorno=entorno_de(inst), host="codex") == (0, "", b"")
        bloqueo = G.correr(evento("git push --force origin main"), entorno=entorno_de(inst), host="codex")
        assert (negado_en_codex(bloqueo) or "").startswith("guard-comandos bloqueó"), "control: %r" % (bloqueo,)


def negado_en_codex(salida):
    codigo, texto, error = salida
    if (codigo, error) != (0, b"") or not texto:
        return None
    try:
        decision = json.loads(texto)
    except ValueError:
        return None
    decision = decision.get("hookSpecificOutput") if isinstance(decision, dict) else None
    if not isinstance(decision, dict) or (decision.get("hookEventName"), decision.get("permissionDecision")) != ("PreToolUse", "deny"):
        return None
    return decision.get("permissionDecisionReason")


def test_codex_preguntar_se_degrada_a_bloquear_y_el_dialecto_sale_de_la_plataforma():
    with carpeta() as base:
        inst, repo = instancia_protegida(base)
        e = evento("git --git-dir C:\\ blame f.sql", cwd=str(repo))
        claude = G.correr(e, entorno=entorno_de(inst))
        assert claude[0] == 0 and json.loads(claude[1])["hookSpecificOutput"]["permissionDecision"] == "ask", "control: Claude pregunta"
        with plataforma("nt"):
            assert G.correr(e, entorno=entorno_de(inst), host="codex") == (0, "", b""), "en PowerShell la barra no escapa"
        with plataforma("posix"):
            salida = G.correr(e, entorno=entorno_de(inst), host="codex")
        texto = negado_en_codex(salida)
        assert texto is not None, "en Codex se bloquea por JSON con exit 0: %r" % (salida,)
        assert texto.startswith("guard-comandos pregunta antes de correr el comando: git ") and "«db»" in texto, texto
        assert texto.endswith("\nCodex no puede pedir confirmación desde un hook, así que este comando queda bloqueado: si hace "
                              "falta, pídele al usuario que lo corra él."), texto


CURVAS_SIMPLES, CURVAS_DOBLES = (chr(0x2018), chr(0x2019)), (chr(0x201C), chr(0x201D))


def en_powershell(comando):
    return G.analizar(_r(comando), None, ENTORNO, None, "PowerShell")


def test_en_powershell_un_backtick_que_escapa_bloquea_como_el_comando_sin_escapes():
    pares = (("g`it push --force origin main", "git push --force origin main"),
             ("git push --f`orce origin main", "git push --force origin main"),
             ("g`it push origin `+main", "git push origin +main"),
             ("git r`eset --har`d", "git reset --hard"),
             ("git cl`ean -fd", "git clean -fd"),
             ("r`m -r C:/fuera/x", "rm -r C:/fuera/x"),
             ("Re`move-Item -Rec`urse -F`orce C:/fuera/x", "Remove-Item -Recurse -Force C:/fuera/x"),
             ("& %sg`it%s push --force origin main" % CURVAS_DOBLES, "& %sgit%s push --force origin main" % CURVAS_DOBLES))
    for escapado, plano in pares:
        esperado = en_powershell(plano)
        assert esperado[0] == "block", "control: %s" % plano
        assert en_powershell(escapado) == esperado, (escapado, en_powershell(escapado), esperado)


def test_el_backtick_de_powershell_bloquea_igual_en_claude_code_y_en_codex():
    escapado, plano = "g`it push --force origin main", "git push --force origin main"
    with carpeta() as base:
        e = entorno_de(instancia(base))
        claude = G.correr(evento(plano, herramienta="PowerShell"), entorno=e)
        assert claude[0] == 2 and claude[2].decode("utf-8").startswith("guard-comandos bloqueó el comando: git push --force"), claude
        assert G.correr(evento(escapado, herramienta="PowerShell"), entorno=e) == claude
        with plataforma("nt"):
            codex = G.correr(evento(plano), entorno=e, host="codex")
            assert (negado_en_codex(codex) or "").startswith("guard-comandos bloqueó el comando: git push --force"), codex
            assert G.correr(evento(escapado), entorno=e, host="codex") == codex
        assert G.correr(evento(escapado, herramienta="Bash"), entorno=e) == (0, "", b""), "en Bash el backtick no es un escape"
        with plataforma("posix"):
            assert G.correr(evento(escapado), entorno=e, host="codex") == (0, "", b""), "Codex en POSIX habla Bash"


def test_en_powershell_el_backtick_no_escapa_entre_comillas_simples_ni_afloja_lo_que_ya_bloqueaba():
    assert en_powershell("git push --`force origin main")[0] is None, "`f es un salto de página: git no recibe --force"
    assert en_powershell("git reset --ha`rd")[0] is None, "`r es un retorno de carro: git no recibe --hard"
    assert en_powershell("rm C:/proyecto/x '-`R'")[0] is None, "entre comillas simples el backtick es literal"
    assert en_powershell("& %sg`it%s push --force origin main" % CURVAS_SIMPLES)[0] is None, "también entre comillas simples curvas"
    assert en_powershell('rm C:/proyecto/x "-`R"')[0] == "block", 'entre comillas dobles escapa, como rm C:/proyecto/x "-R"'
    assert en_powershell("Write-Output \"it's\"; g`it push --force origin main")[0] == "block", "un ' entre comillas dobles es literal"
    curvas = "Write-Output %sit's%s; g`it push --force origin main" % CURVAS_DOBLES
    assert en_powershell(curvas)[0] == "block", "también entre comillas dobles curvas"
    assert en_powershell("Write-Output @'\nit's ok\nr`m -r C:/x\n'@")[0] is None, "un here-string @'...'@ es literal"
    doble = 'Write-Output @"\nsay "it\'s", ok\n"@; g`it push --force origin main'
    assert en_powershell(doble)[0] == "block", 'las comillas dentro de un @"..."@ no cierran'
    assert en_powershell("Remove-Item -Recurse -Force %s\\x`y" % bw(SCR))[0] == "block", "lo que ya bloqueaba sigue bloqueando"


def test_en_powershell_los_casos_del_origen_dan_la_misma_decision():
    if not NT:
        print("      (el dialecto PowerShell fuera de Windows está fuera de dominio: lo prueba el CI de Windows)")
        return
    with mundo() as m:
        tabla = valores(m.equipo)
        prot = m.protegidos()
        fallos = []
        for nombre, comando, cwd, esperado in CASOS:
            resultado, motivo = G.analizar(_r(comando, tabla), _cwd(cwd, tabla), ENTORNO, prot, "PowerShell")
            if resultado != ESPERADO[esperado]:
                fallos.append("  %s: esperado %s, salio %s (%s)" % (nombre, esperado, resultado, motivo))
    assert not fallos, "%d fallos\n" % len(fallos) + "\n".join(fallos)


def test_un_host_desconocido_bloquea_en_pre_aunque_no_haya_instancia():
    for host in ("otro", "", None):
        codigo, salida, error = G.correr(evento("ls"), entorno=dict(ENTORNO), host=host)
        assert (codigo, salida) == (2, "") and error.startswith(b"odd-ws: host desconocido"), (host, error)
    assert G.correr(evento("ls", hook_event_name="PostToolUse"), entorno=dict(ENTORNO), host="otro") == (0, "", b"")
    with carpeta() as base:
        inst = instancia(base)
        entorno = dict(os.environ, **entorno_de(inst))

        def hook(e, *args):
            return subprocess.run([sys.executable, str(_RUTA), "--plazo", "8", *args], input=json.dumps(e).encode("utf-8"),
                                  capture_output=True, env=entorno, cwd=str(base), timeout=60)

        r = hook(evento("git status"), "--host", "gemini")
        assert r.returncode == 2 and r.stderr.startswith(b"odd-ws: host desconocido") and b"'gemini'" in r.stderr, r
        r = hook(evento("git status"), "--host")
        assert r.returncode == 2 and b"sin valor" in r.stderr, r
        r = hook(evento("git push --force origin main"), "--host", "codex")
        assert (negado_en_codex((r.returncode, r.stdout.decode("ascii"), r.stderr)) or "").startswith("guard-comandos bloqueó"), r
        r = hook(evento("git status"), "--host", "codex")
        assert (r.returncode, r.stdout, r.stderr) == (0, b"", b""), r
        r = hook(evento("git status"), "--host=gemini")
        assert r.returncode == 2 and r.stderr.startswith(b"odd-ws: host desconocido") and b"'gemini'" in r.stderr, r
        r = hook(evento("git status"), "--host=")
        assert r.returncode == 2 and r.stderr.startswith(b"odd-ws: host desconocido"), r


def main():
    for flujo in (sys.stdout, sys.stderr):
        flujo.reconfigure(encoding="utf-8", errors="replace")
    pruebas = [(nombre, funcion) for nombre, funcion in globals().items() if nombre.startswith("test_") and callable(funcion)]
    fallas = 0
    for nombre, prueba in pruebas:
        try:
            prueba()
            print(f"ok    {nombre}")
        except AssertionError as error:
            fallas += 1
            print(f"FALLA {nombre}: {error}")
        except Exception as error:
            fallas += 1
            print(f"ERROR {nombre}: {type(error).__name__}: {error}")
    if SOBRANTES:
        fallas += 1
        print("TEMPORALES SIN BORRAR: %s" % ", ".join(SOBRANTES))
    print(f"{len(pruebas) - fallas}/{len(pruebas)} pruebas en verde")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
