import li.cil.repack.org.luaj.vm2.*;
import li.cil.repack.org.luaj.vm2.lib.jse.JsePlatform;

public class RunLua {
    public static void main(String[] a) throws Exception {
        Globals g = JsePlatform.standardGlobals();
        g.get("dofile").call(LuaValue.valueOf(a[0]));
    }
}
