import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.address.*;
import ghidra.program.model.symbol.*;
import ghidra.util.task.ConsoleTaskMonitor;
import java.io.*;
import java.util.*;

public class DumpDecomp extends GhidraScript {
  public void run() throws Exception {
    // Working dir: first script arg if given, else the analyzeHeadless invocation dir.
    String[] sargs = getScriptArgs();
    String BASE = sargs.length > 0 ? sargs[0] : System.getProperty("user.dir");
    File tf = new File(BASE, "ghidra_targets.txt");
    File of = new File(BASE, "ghidra_out.txt");
    DecompInterface dec = new DecompInterface();
    dec.openProgram(currentProgram);
    FunctionManager fm = currentProgram.getFunctionManager();
    ReferenceManager ref = currentProgram.getReferenceManager();
    AddressFactory af = currentProgram.getAddressFactory();
    StringBuilder sb = new StringBuilder();
    BufferedReader br = new BufferedReader(new FileReader(tf));
    String line;
    while ((line = br.readLine()) != null) {
      line = line.trim();
      if (line.isEmpty() || line.startsWith("#")) continue;
      String[] p = line.split("\\s+", 2);
      long a = Long.parseLong(p[0].replace("0x", ""), 16);
      Address ad = af.getDefaultAddressSpace().getAddress(a);
      Function f = fm.getFunctionContaining(ad);
      sb.append("\n========================================================\n");
      if (f == null) { sb.append("ADDR " + p[0] + " -> NO FUNCTION\n"); continue; }
      sb.append("FUNC " + f.getName() + "  entry=" + f.getEntryPoint() + "  " + (p.length > 1 ? p[1] : "") + "\n");
      Set<String> callers = new TreeSet<>();
      for (Reference r : ref.getReferencesTo(f.getEntryPoint())) {
        Function cf = fm.getFunctionContaining(r.getFromAddress());
        callers.add(r.getFromAddress() + "@" + (cf != null ? cf.getName() : "?"));
      }
      sb.append("CALLERS(" + callers.size() + "): " + String.join(", ", callers) + "\n");
      DecompileResults res = dec.decompileFunction(f, 60, new ConsoleTaskMonitor());
      if (res != null && res.decompileCompleted()) sb.append(res.getDecompiledFunction().getC());
      else sb.append("// decompile failed\n");
    }
    br.close();
    FileWriter w = new FileWriter(of); w.write(sb.toString()); w.close();
    println("DumpDecomp wrote to " + of);
  }
}
