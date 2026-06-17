import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.*;
import ghidra.program.model.address.*;
import ghidra.program.model.symbol.*;
import java.io.*;
import java.util.*;

public class FindDataRefs extends GhidraScript {
  public void run() throws Exception {
    // Working dir: first script arg if given, else the analyzeHeadless invocation dir.
    String[] sargs = getScriptArgs();
    String BASE = sargs.length > 0 ? sargs[0] : System.getProperty("user.dir");
    BufferedReader br = new BufferedReader(new FileReader(new File(BASE, "ghidra_data_targets.txt")));
    FunctionManager fm = currentProgram.getFunctionManager();
    ReferenceManager ref = currentProgram.getReferenceManager();
    AddressFactory af = currentProgram.getAddressFactory();
    StringBuilder sb = new StringBuilder();
    String line;
    while ((line = br.readLine()) != null) {
      line = line.trim();
      if (line.isEmpty() || line.startsWith("#")) continue;
      String[] p = line.split("\\s+", 2);
      long a = Long.parseLong(p[0].replace("0x", ""), 16);
      Address ad = af.getDefaultAddressSpace().getAddress(a);
      sb.append("\n=== refs to " + p[0] + "  " + (p.length>1?p[1]:"") + " ===\n");
      ReferenceIterator it = ref.getReferencesTo(ad);
      Map<String,String> perFunc = new TreeMap<>();
      while (it.hasNext()) {
        Reference r = it.next();
        Function f = fm.getFunctionContaining(r.getFromAddress());
        String fn = (f != null ? f.getName() + "@" + f.getEntryPoint() : "?");
        String rw = r.getReferenceType().isWrite() ? "W" : (r.getReferenceType().isRead() ? "R" : "?");
        perFunc.merge(fn, rw + "@" + r.getFromAddress(), (x,y)->x+" "+y);
      }
      for (Map.Entry<String,String> e : perFunc.entrySet())
        sb.append("  " + e.getKey() + " : " + e.getValue() + "\n");
    }
    br.close();
    FileWriter w = new FileWriter(new File(BASE, "ghidra_data_out.txt")); w.write(sb.toString()); w.close();
    println("FindDataRefs done");
  }
}
