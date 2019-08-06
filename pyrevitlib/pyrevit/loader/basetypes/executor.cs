using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using System.Runtime.Remoting;
using System.Reflection;
using Autodesk.Revit.UI;
using Autodesk.Revit.DB;
using Autodesk.Revit.ApplicationServices;

// iron languages
using Microsoft.Scripting;
using Microsoft.Scripting.Hosting;
using IronPython.Runtime.Exceptions;
using IronPython.Compiler;
//using IronRuby;

// cpython
using Python.Runtime;

// csharp
using System.CodeDom.Compiler;
using Microsoft.CSharp;
//vb
using Microsoft.VisualBasic;


namespace PyRevitBaseClasses {
    /// Executes a script
    public class ScriptExecutor {
        /// Run the script and print the output to a new output window.
        public static int ExecuteScript(ref PyRevitScriptRuntime pyrvtScript) {
            switch (pyrvtScript.EngineType) {
                case EngineType.IronPython:
                    return ExecuteIronPythonScript(ref pyrvtScript);
                case EngineType.CPython:
                    return ExecuteCPythonScript(ref pyrvtScript);
                case EngineType.CSharp:
                    return ExecuteCLRScript(ref pyrvtScript);
                case EngineType.Invoke:
                    return ExecuteInvokableDLL(ref pyrvtScript);
                case EngineType.VisualBasic:
                    return ExecuteCLRScript(ref pyrvtScript);
                case EngineType.IronRuby:
                    return ExecuteRubyScript(ref pyrvtScript);
                case EngineType.Dynamo:
                    return ExecuteDynamoDefinition(ref pyrvtScript);
                case EngineType.Grasshopper:
                    return ExecuteGrasshopperDocument(ref pyrvtScript);
                default:
                    // should not get here
                    throw new Exception("Unknown engine type.");
            }
        }

        /// Run the script using IronPython Engine
        private static int ExecuteIronPythonScript(ref PyRevitScriptRuntime pyrvtScript) {
            // 1: ----------------------------------------------------------------------------------------------------
            // get new engine manager (EngineManager manages document-specific engines)
            // and ask for an engine (EngineManager return either new engine or an already active one)
            var engineMgr = new IronPythonEngineManager();
            var engine = engineMgr.GetEngine(ref pyrvtScript);

            // 2: ----------------------------------------------------------------------------------------------------
            // Setup the command scope in this engine with proper builtin and scope parameters
            var scope = engine.CreateScope();

            // 3: ----------------------------------------------------------------------------------------------------
            // Create the script from source file
            var script = engine.CreateScriptSourceFromFile(
                    pyrvtScript.ScriptSourceFile,
                    System.Text.Encoding.UTF8,
                    SourceCodeKind.File
                );

            // 4: ----------------------------------------------------------------------------------------------------
            // Setting up error reporter and compile the script
            // setting module to be the main module so __name__ == __main__ is True
            var compiler_options = (PythonCompilerOptions)engine.GetCompilerOptions(scope);
            compiler_options.ModuleName = "__main__";
            compiler_options.Module |= IronPython.Runtime.ModuleOptions.Initialize;

            var errors = new IronPythonErrorReporter();
            var command = script.Compile(compiler_options, errors);

            // Process compile errors if any
            if (command == null) {
                // compilation failed, print errors and return
                pyrvtScript.OutputStream.WriteError(
                    string.Join("\n", ExternalConfig.ipyerrtitle, string.Join("\n", errors.Errors.ToArray()))
                    );
                return ExecutionResultCodes.CompileException;
            }

            // 6: ----------------------------------------------------------------------------------------------------
            // Finally let's execute
            try {
                command.Execute(scope);
                return ExecutionResultCodes.Succeeded;
            }
            catch (SystemExitException) {
                // ok, so the system exited. That was bound to happen...
                return ExecutionResultCodes.SysExited;
            }
            catch (Exception exception) {
                // show (power) user everything!
                string _clr_err_message = exception.ToString();
                string _ipy_err_messages = engine.GetService<ExceptionOperations>().FormatException(exception);

                // Print all errors to stdout and return cancelled to Revit.
                // This is to avoid getting window prompts from Revit.
                // Those pop ups are small and errors are hard to read.
                _ipy_err_messages = _ipy_err_messages.Replace("\r\n", "\n");
                pyrvtScript.IronLanguageTraceBack = _ipy_err_messages;

                _clr_err_message = _clr_err_message.Replace("\r\n", "\n");
                pyrvtScript.CLRTraceBack = _clr_err_message;

                _ipy_err_messages = string.Join("\n", ExternalConfig.ipyerrtitle, _ipy_err_messages);
                _clr_err_message = string.Join("\n", ExternalConfig.clrerrtitle, _clr_err_message);

                pyrvtScript.OutputStream.WriteError(_ipy_err_messages + "\n\n" + _clr_err_message);
                return ExecutionResultCodes.ExecutionException;
            }
            finally {
                // clean the scope unless the script is requesting clean engine
                // this is a temporary convention to allow users to keep global references in the scope
                if (!pyrvtScript.NeedsCleanEngine) {
                    var cleanupScript = engine.CreateScriptSourceFromString(
                        "for __deref in dir():\n" +
                        "    if not __deref.startswith('__'):\n" +
                        "        del globals()[__deref]");
                    cleanupScript.Compile();
                    cleanupScript.Execute(scope);
                }

                engineMgr.CleanupEngine(engine);
            }
        }

        /// Run the script using CPython Engine
        private static int ExecuteCPythonScript(ref PyRevitScriptRuntime pyrvtScript) {
            using (Py.GIL()) {
                // initialize
                if (!PythonEngine.IsInitialized)
                    PythonEngine.Initialize();

                // set output stream
                dynamic sys = PythonEngine.ImportModule("sys");
                sys.stdout = pyrvtScript.OutputStream;

                // TODO: implement globals like ironpython
                // set uiapplication
                sys.host = pyrvtScript.UIApp;
                var locals = new PyDict();
                locals["__file__"] = pyrvtScript.ScriptSourceFile.ToPython();

                // run
                try {
                    var scriptContents = File.ReadAllText(pyrvtScript.ScriptSourceFile);
                    PythonEngine.Exec(scriptContents, locals: locals.Handle);
                    return ExecutionResultCodes.Succeeded;
                }
                catch (Exception cpyex) {
                    string _cpy_err_message = cpyex.Message;
                    // Print all errors to stdout and return cancelled to Revit.
                    // This is to avoid getting window prompts from Revit.
                    // Those pop ups are small and errors are hard to read.
                    _cpy_err_message = _cpy_err_message.Replace("\r\n", "\n");
                    pyrvtScript.CpythonTraceBack = _cpy_err_message;

                    pyrvtScript.OutputStream.WriteError(_cpy_err_message);
                    return ExecutionResultCodes.ExecutionException;
                }
                finally {
                    // shutdown halts and breaks Revit
                    // let's not do that!
                    // PythonEngine.Shutdown();
                }
            }
        }

        /// Run the script using C# or VisualBasic script engine
        private static int ExecuteCLRScript(ref PyRevitScriptRuntime pyrvtScript) {
            // compile first
            Assembly scriptAssm = null;
            try {
                scriptAssm = CompileCLRScript(ref pyrvtScript);
            }
            catch (Exception compileEx) {
                string _clr_err_message = compileEx.ToString();
                _clr_err_message = _clr_err_message.Replace("\r\n", "\n");
                pyrvtScript.CLRTraceBack = _clr_err_message;

                // TODO: change to script output for all script types
                if (pyrvtScript.InterfaceType == InterfaceType.ExternalCommand)
                    TaskDialog.Show("pyRevit", pyrvtScript.CLRTraceBack);

                TaskDialog.Show("pyRevit", pyrvtScript.CLRTraceBack);

                return ExecutionResultCodes.CompileException;
            }

            // scriptAssm must have value
            switch (pyrvtScript.InterfaceType) {
                // if is an external command
                case InterfaceType.ExternalCommand:
                    try {
                        var resultCode = ExecuteExternalCommand(scriptAssm, null, ref pyrvtScript);
                        if (resultCode == ExecutionResultCodes.ExternalInterfaceNotImplementedException)
                            TaskDialog.Show("pyRevit",
                                string.Format(
                                    "Can not find any type implementing IExternalCommand in assembly \"{0}\"",
                                    scriptAssm.Location
                                    ));
                        return resultCode;
                    }
                    catch (Exception execEx) {
                        string _clr_err_message = execEx.ToString();
                        _clr_err_message = _clr_err_message.Replace("\r\n", "\n");
                        pyrvtScript.CLRTraceBack = _clr_err_message;
                        // TODO: same outp
                        TaskDialog.Show("pyRevit", _clr_err_message);

                        return ExecutionResultCodes.ExecutionException;
                    }

                // if is an event hook
                case InterfaceType.EventHandler:
                    try {
                        return ExecuteEventHandler(scriptAssm, ref pyrvtScript);
                    }
                    catch (Exception execEx) {
                        string _clr_err_message = execEx.ToString();
                        _clr_err_message = _clr_err_message.Replace("\r\n", "\n");
                        pyrvtScript.CLRTraceBack = _clr_err_message;

                        TaskDialog.Show("pyRevit", pyrvtScript.CLRTraceBack);
                        return ExecutionResultCodes.ExecutionException;
                    }

                default:
                    return ExecutionResultCodes.ExternalInterfaceNotImplementedException;
            }
        }

        /// Run the script by directly invoking the IExternalCommand type from given dll
        private static int ExecuteInvokableDLL(ref PyRevitScriptRuntime pyrvtScript) {
            try {
                if (pyrvtScript.ConfigScriptSourceFile != null || pyrvtScript.ConfigScriptSourceFile != string.Empty) {
                    // load the binary data from the DLL
                    // Direct invoke commands use the config script source file to point
                    // to the target dll assembly location
                    string assmFile = pyrvtScript.ConfigScriptSourceFile;
                    string className = null;
                    if (pyrvtScript.ConfigScriptSourceFile.Contains("::")) {
                        var parts = pyrvtScript.ConfigScriptSourceFile.Split(
                            new string[] { "::" },
                            StringSplitOptions.RemoveEmptyEntries
                            );
                        assmFile = parts[0];
                        className = parts[1];
                    }

                    byte[] assmBin = File.ReadAllBytes(assmFile);
                    Assembly assmObj = Assembly.Load(assmBin);

                    var resultCode = ExecuteExternalCommand(assmObj, className, ref pyrvtScript);
                    if (resultCode == ExecutionResultCodes.ExternalInterfaceNotImplementedException)
                        TaskDialog.Show("pyRevit",
                            string.Format(
                                "Can not find type \"{0}\" in assembly \"{1}\"",
                                className,
                                assmObj.Location
                                ));
                    return resultCode;
                }
                else {
                    TaskDialog.Show("pyRevit", "Target assembly is not set correctly and can not be loaded.");
                    return ExecutionResultCodes.ExternalInterfaceNotImplementedException;
                }
            }
            catch (Exception invokeEx) {
                TaskDialog.Show("pyRevit", invokeEx.Message);
                return ExecutionResultCodes.ExecutionException;
            }
            finally {
                // whatever
            }
        }

        /// Run the script using ruby script engine
        private static int ExecuteRubyScript(ref PyRevitScriptRuntime pyrvtScript) {
            // TODO: ExecuteRubyScript
            TaskDialog.Show("pyRevit", "Ruby-Script Execution Engine Not Yet Implemented.");
            return ExecutionResultCodes.EngineNotImplementedException;
            //// https://github.com/hakonhc/RevitRubyShell/blob/master/RevitRubyShell/RevitRubyShellApplication.cs
            //// 1: ----------------------------------------------------------------------------------------------------
            //// start ruby interpreter
            //var engine = Ruby.CreateEngine();
            //var scope = engine.CreateScope();

            //// 2: ----------------------------------------------------------------------------------------------------
            //// Finally let's execute
            //try {
            //    // Run the code
            //    engine.ExecuteFile(pyrvtScript.ScriptSourceFile, scope);
            //    return ExecutionErrorCodes.Succeeded;
            //}
            //catch (SystemExitException) {
            //    // ok, so the system exited. That was bound to happen...
            //    return ExecutionErrorCodes.SysExited;
            //}
            //catch (Exception exception) {
            //    // show (power) user everything!
            //    string _dotnet_err_message = exception.ToString();
            //    string _ruby_err_messages = engine.GetService<ExceptionOperations>().FormatException(exception);

            //    // Print all errors to stdout and return cancelled to Revit.
            //    // This is to avoid getting window prompts from Revit.
            //    // Those pop ups are small and errors are hard to read.
            //    _ruby_err_messages = _ruby_err_messages.Replace("\r\n", "\n");
            //    pyrvtScript.IronLanguageTraceBack = _ruby_err_messages;

            //    _dotnet_err_message = _dotnet_err_message.Replace("\r\n", "\n");
            //    pyrvtScript.ClrTraceBack = _dotnet_err_message;

            //    _ruby_err_messages = string.Join("\n", ExternalConfig.irubyerrtitle, _ruby_err_messages);
            //    _dotnet_err_message = string.Join("\n", ExternalConfig.dotneterrtitle, _dotnet_err_message);

            //    pyrvtScript.OutputStream.WriteError(_ruby_err_messages + "\n\n" + _dotnet_err_message);
            //    return ExecutionErrorCodes.ExecutionException;
            //}
            //finally {
            //    // whatever
            //}
        }

        /// Run the script using DynamoBIM
        private static int ExecuteDynamoDefinition(ref PyRevitScriptRuntime pyrvtScript) {
            var journalData = new Dictionary<string, string>() {
                // Specifies the path to the Dynamo workspace to execute.
                { "dynPath", pyrvtScript.ScriptSourceFile },

                // Specifies whether the Dynamo UI should be visible (set to false - Dynamo will run headless).
                { "dynShowUI", pyrvtScript.DebugMode.ToString() },

                // If the journal file specifies automation mode
                // Dynamo will run on the main thread without the idle loop.
                { "dynAutomation",  "True" },

                // The journal file can specify if the Dynamo workspace opened
                //{ "dynForceManualRun",  "True" }

                // The journal file can specify if the Dynamo workspace opened from DynPathKey will be executed or not. 
                // If we are in automation mode the workspace will be executed regardless of this key.
                { "dynPathExecute",  "True" },

                // The journal file can specify if the existing UIless RevitDynamoModel
                // needs to be shutdown before performing any action.
                // per comments on https://github.com/eirannejad/pyRevit/issues/570
                // Setting this to True slows down Dynamo by a factor of 3
                { "dynModelShutDown",  "True" },

                // The journal file can specify the values of Dynamo nodes.
                //{ "dynModelNodesInfo",  "" }
                };

            //return new DynamoRevit().ExecuteCommand(new DynamoRevitCommandData() {
            //    JournalData = journalData,
            //    Application = commandData.Application
            //});

            try {
                // find the DynamoRevitApp from DynamoRevitDS.dll
                // this should be already loaded since Dynamo loads before pyRevit
                ObjectHandle dynRevitAppObjHandle =
                    Activator.CreateInstance("DynamoRevitDS", "Dynamo.Applications.DynamoRevitApp");
                object dynRevitApp = dynRevitAppObjHandle.Unwrap();
                MethodInfo execDynamo = dynRevitApp.GetType().GetMethod("ExecuteDynamoCommand");

                // run the script
                execDynamo.Invoke(dynRevitApp, new object[] { journalData, pyrvtScript.UIApp });
                return ExecutionResultCodes.Succeeded;
            }
            catch (FileNotFoundException) {
                // if failed in finding DynamoRevitDS.dll, assume no dynamo
                TaskDialog.Show("pyRevit",
                    "Can not find dynamo installation or determine which Dynamo version to Run.\n\n" +
                    "Run Dynamo once to select the active version.");
                return ExecutionResultCodes.ExecutionException;
            }
        }

        /// Run the script using Grasshopper
        private static int ExecuteGrasshopperDocument(ref PyRevitScriptRuntime pyrvtScript) {
            // TODO: ExecuteGrasshopperDocument
            TaskDialog.Show("pyRevit", "Grasshopper Execution Engine Not Yet Implemented.");
            return ExecutionResultCodes.EngineNotImplementedException;
        }

        // utility methods -------------------------------------------------------------------------------------------
        // clr scripts
        private static IEnumerable<Type> GetTypesSafely(Assembly assembly) {
            try {
                return assembly.GetTypes();
            }
            catch (ReflectionTypeLoadException ex) {
                return ex.Types.Where(x => x != null);
            }
        }

        private static Assembly CompileCLRScript(ref PyRevitScriptRuntime pyrvtScript) {
            // https://stackoverflow.com/a/3188953
            // read the script
            var scriptContents = File.ReadAllText(pyrvtScript.ScriptSourceFile);

            // read the referenced dlls from env vars
            // pyrevit sets this when loading
            string[] refFiles;
            var envDic = new EnvDictionary();
            if (envDic.ReferencedAssemblies.Count() == 0) {
                var refs = AppDomain.CurrentDomain.GetAssemblies();
                refFiles = refs.Select(a => a.Location).ToArray();
            }
            else {
                refFiles = envDic.ReferencedAssemblies;
            }

            // create compiler parameters
            var compileParams = new CompilerParameters(refFiles);
            compileParams.CompilerOptions = string.Format("/optimize -define:REVIT{0}", pyrvtScript.App.VersionNumber);
            compileParams.GenerateInMemory = true;
            compileParams.GenerateExecutable = false;

            // determine which code provider to use
            CodeDomProvider compiler;
            var compConfig = new Dictionary<string, string>() { { "CompilerVersion", "v4.0" } };
            switch (pyrvtScript.EngineType) {
                case EngineType.CSharp:
                    compiler = new CSharpCodeProvider(compConfig);
                    break;
                case EngineType.VisualBasic:
                    compiler = new VBCodeProvider(compConfig);
                    break;
                default:
                    throw new Exception("Specified language does not have a compiler.");
            }

            // compile code first
            var res = compiler.CompileAssemblyFromSource(
                options: compileParams,
                sources: new string[] { scriptContents }
            );

            // now run
            return res.CompiledAssembly;
        }

        private static int ExecuteExternalCommand(Assembly assmObj, string className, ref PyRevitScriptRuntime pyrvtScript) {
            foreach (Type assmType in GetTypesSafely(assmObj)) {
                if (assmType.IsClass) {
                    // find the appropriate type and execute
                    if (className != null) {
                        if (assmType.Name == className)
                            return ExecuteExternalCommandType(assmType, ref pyrvtScript);
                        else
                            continue;
                    }
                    else if (assmType.GetInterfaces().Contains(typeof(IExternalCommand)))
                        return ExecuteExternalCommandType(assmType, ref pyrvtScript);
                }
            }

            return ExecutionResultCodes.ExternalInterfaceNotImplementedException;
        }

        private static int ExecuteExternalCommandType(Type extCommandType, ref PyRevitScriptRuntime pyrvtScript) {
            // execute
            object extCommandInstance = Activator.CreateInstance(extCommandType);
            string commandMessage = string.Empty;
            extCommandType.InvokeMember(
                "Execute",
                BindingFlags.Default | BindingFlags.InvokeMethod,
                null,
                extCommandInstance,
                new object[] {
                pyrvtScript.CommandData,
                commandMessage,
                pyrvtScript.SelectedElements}
                );
            return ExecutionResultCodes.Succeeded;
        }

        private static int ExecuteEventHandler(Assembly assmObj, ref PyRevitScriptRuntime pyrvtScript) {
            foreach (Type assmType in GetTypesSafely(assmObj))
                foreach (MethodInfo methodInfo in assmType.GetMethods()) {
                    var methodParams = methodInfo.GetParameters();
                    if (methodParams.Count() == 2
                                && methodParams[0].Name == "sender"
                                && (methodParams[1].Name == "e" || methodParams[1].Name == "args")) {
                        methodInfo.Invoke(
                            null,
                            new object[] {
                                    pyrvtScript.EventSender,
                                    pyrvtScript.EventArgs
                                }
                            );
                        return ExecutionResultCodes.Succeeded;
                    }
                }

            return ExecutionResultCodes.ExternalInterfaceNotImplementedException;
        }
    }

    public class IronPythonErrorReporter : ErrorListener {
        public List<string> Errors = new List<string>();

        public override void ErrorReported(ScriptSource source, string message,
                                           SourceSpan span, int errorCode, Severity severity) {
            Errors.Add(string.Format("{0} (line {1})", message, span.Start.Line));
        }

        public int Count {
            get { return Errors.Count; }
        }
    }

}
