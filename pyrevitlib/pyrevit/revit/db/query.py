"""Helper functions to query info and elements from Revit."""
#pylint: disable=W0703,C0103
from collections import namedtuple

from pyrevit.coreutils import logger
from pyrevit import HOST_APP, PyRevitException
from pyrevit import framework
from pyrevit.compat import safe_strtype
from pyrevit import DB
from pyrevit.revit import db

from Autodesk.Revit.DB import Element   #pylint: disable=E0401


mlogger = logger.get_logger(__name__)


GRAPHICAL_VIEWTYPES = [
    DB.ViewType.FloorPlan,
    DB.ViewType.CeilingPlan,
    DB.ViewType.Elevation,
    DB.ViewType.ThreeD,
    DB.ViewType.Schedule,
    DB.ViewType.DrawingSheet,
    DB.ViewType.Report,
    DB.ViewType.DraftingView,
    DB.ViewType.Legend,
    DB.ViewType.EngineeringPlan,
    DB.ViewType.AreaPlan,
    DB.ViewType.Section,
    DB.ViewType.Detail,
    DB.ViewType.CostReport,
    DB.ViewType.LoadsReport,
    DB.ViewType.PresureLossReport,
    DB.ViewType.ColumnSchedule,
    DB.ViewType.PanelSchedule,
    DB.ViewType.Walkthrough,
    DB.ViewType.Rendering
]


DETAIL_CURVES = (
    DB.DetailLine,
    DB.DetailArc,
    DB.DetailEllipse,
    DB.DetailNurbSpline
)

MODEL_CURVES = (
    DB.ModelLine,
    DB.ModelArc,
    DB.ModelEllipse,
    DB.ModelNurbSpline
)

BUILTINCATEGORIES_VIEW = [
    DB.BuiltInCategory.OST_Views,
    DB.BuiltInCategory.OST_ReferenceViewer,
    DB.BuiltInCategory.OST_Viewers
]

GridPoint = namedtuple('GridPoint', ['point', 'grids'])

SheetRefInfo = namedtuple('SheetRefInfo',
                          ['sheet_num', 'sheet_name', 'detail_num',
                           'ref_viewid'])

ElementHistory = namedtuple('ElementHistory',
                            ['creator', 'owner', 'last_changed_by'])


def get_name(element, title_on_sheet=False):
    # grab viewname correctly
    if isinstance(element, DB.View):
        view_name = None
        if title_on_sheet:
            titleos_param = \
                element.Parameter[DB.BuiltInParameter.VIEW_DESCRIPTION]
            view_name = titleos_param.AsString()

        # if view name could bot be extracted from title_on_sheet
        if view_name:
            return view_name
        else:
            if HOST_APP.is_newer_than('2019', or_equal=True):
                return element.Name
            else:
                return element.ViewName

    # have to use the imported Element otherwise
    # AttributeError occurs
    return Element.Name.__get__(element)


def get_type(element):
    """Get element type.

    Args:
        element (DB.Element): source element

    Returns:
        DB.ElementType: type object of given element
    """
    type_id = element.GetTypeId()
    return element.Document.GetElement(type_id)


def get_symbol_name(element):
    return get_name(element.Symbol)


def get_family_name(element):
    return get_name(element.Symbol.Family)


def get_param(element, param_name, default=None):
    if isinstance(element, DB.Element):
        try:
            return element.LookupParameter(param_name)
        except Exception:
            return default


def get_assoc_doc(element):
    return element.Document


def get_mark(element):
    mparam = element.Parameter[DB.BuiltInParameter.ALL_MODEL_MARK]
    return mparam.AsString() if mparam else ''


def get_location(element):
    locp = element.Location.Point
    return (locp.X, locp.Y, locp.Z)


def get_biparam_stringequals_filter(bip_paramvalue_dict):
    filters = []
    for bip, fvalue in bip_paramvalue_dict.items():
        bip_id = DB.ElementId(bip)
        bip_valueprovider = DB.ParameterValueProvider(bip_id)
        bip_valuerule = DB.FilterStringRule(bip_valueprovider,
                                            DB.FilterStringEquals(),
                                            fvalue,
                                            True)
        filters.append(bip_valuerule)

    if filters:
        return DB.ElementParameterFilter(
            framework.List[DB.FilterRule](filters)
            )
    else:
        raise PyRevitException('Error creating filters.')


def get_all_elements(doc=None):
            #  .WhereElementIsNotElementType()\
    return DB.FilteredElementCollector(doc or HOST_APP.doc)\
             .WherePasses(
                 DB.LogicalOrFilter(
                     DB.ElementIsElementTypeFilter(False),
                     DB.ElementIsElementTypeFilter(True)))\
             .ToElements()


def get_all_elements_in_view(view):
    return DB.FilteredElementCollector(view.Document, view.Id)\
             .WhereElementIsNotElementType()\
             .ToElements()


def get_param_value(targetparam):
    if targetparam.StorageType == DB.StorageType.Double:
        value = targetparam.AsDouble()
    elif targetparam.StorageType == DB.StorageType.Integer:
        value = targetparam.AsInteger()
    elif targetparam.StorageType == DB.StorageType.String:
        value = targetparam.AsString()
    elif targetparam.StorageType == DB.StorageType.ElementId:
        value = targetparam.AsElementId()

    return value


def get_value_range(param_name, doc=None):
    values = set()
    for element in get_all_elements(doc):
        targetparam = element.LookupParameter(param_name)
        if targetparam:
            value = get_param_value(targetparam)
            if value is not None \
                    and safe_strtype(value).lower() != 'none':
                if isinstance(value, str) \
                        and not value.isspace():
                    values.add(value)
                else:
                    values.add(value)
    return values


def get_elements_by_parameter(param_name, param_value,
                              doc=None, partial=False):
    # does not work in < 2016
    # spid = framework.Guid('24353a46-1313-46a4-a779-d33ffe9353ab')
    # pid = DB.SharedParameterElement.Lookup(revit.doc, spid)
    # pp = DB.ParameterValueProvider(pid)
    # pe = DB.FilterStringEquals()
    # vrule = DB.FilterDoubleRule(pp, pe, scope_id, True)
    # param_filter = DB.ElementParameterFilter(vrule)
    # elements = DB.FilteredElementCollector(revit.doc) \
    #           .WherePasses(param_filter) \
    #           .ToElementIds()

    found_els = []
    for element in get_all_elements(doc):
        targetparam = element.LookupParameter(param_name)
        if targetparam:
            value = get_param_value(targetparam)
            if partial \
                    and value is not None \
                    and isinstance(value, str) \
                    and param_value in value:
                found_els.append(element)
            elif param_value == value:
                found_els.append(element)
    return found_els


def get_elements_by_param_value(param_name, param_value,
                                inverse=False, doc=None):
    doc = doc or HOST_APP.doc
    param_id = get_project_parameter_id(param_name)
    if param_id:
        pvprov = DB.ParameterValueProvider(param_id)
        pfilter = DB.FilterStringEquals()
        vrule = DB.FilterStringRule(pvprov, pfilter, param_value, True)
        if inverse:
            vrule = DB.FilterInverseRule(vrule)
        param_filter = DB.ElementParameterFilter(vrule)
        return DB.FilteredElementCollector(doc)\
                 .WherePasses(param_filter)\
                 .ToElements()
    else:
        return []


def get_elements_by_category(element_bicats, elements=None, doc=None):
    # if source elements is provided
    if elements:
        return [x for x in elements
                if get_builtincategory(x.Category.Name)
                in element_bicats]

    # otherwise collect from model
    cat_filters = [DB.ElementCategoryFilter(x) for x in element_bicats]
    elcats_filter = \
        DB.LogicalOrFilter(framework.List[DB.ElementFilter](cat_filters))
    return DB.FilteredElementCollector(doc or HOST_APP.doc)\
             .WherePasses(elcats_filter)\
             .WhereElementIsNotElementType()\
             .ToElements()


def get_elements_by_class(element_class, elements=None, doc=None, view_id=None):
    # if source elements is provided
    if elements:
        return [x for x in elements if isinstance(x, element_class)]

    # otherwise collect from model
    if view_id:
        return DB.FilteredElementCollector(doc or HOST_APP.doc, view_id)\
                 .OfClass(element_class)\
                 .WhereElementIsNotElementType()\
                 .ToElements()
    else:
        return DB.FilteredElementCollector(doc or HOST_APP.doc)\
                .OfClass(element_class)\
                .WhereElementIsNotElementType()\
                .ToElements()


def get_types_by_class(type_class, types=None, doc=None):
    # if source types is provided
    if types:
        return [x for x in types if isinstance(x, type_class)]

    # otherwise collect from model
    return DB.FilteredElementCollector(doc or HOST_APP.doc)\
            .OfClass(type_class)\
            .ToElements()


def get_family(family_name, doc=None):
    famsyms = \
        DB.FilteredElementCollector(doc or HOST_APP.doc)\
          .WherePasses(
              get_biparam_stringequals_filter(
                  {DB.BuiltInParameter.SYMBOL_FAMILY_NAME_PARAM: family_name}
                  )
              )\
          .WhereElementIsElementType()\
          .ToElements()
    return famsyms


def get_noteblock_families(doc=None):
    doc = doc or HOST_APP.doc
    return [doc.GetElement(x)
            for x in DB.ViewSchedule.GetValidFamiliesForNoteBlock(doc)]


def get_elements_by_family(family_name, doc=None):
    famsyms = \
        DB.FilteredElementCollector(doc or HOST_APP.doc)\
          .WherePasses(
              get_biparam_stringequals_filter(
                  {DB.BuiltInParameter.SYMBOL_FAMILY_NAME_PARAM: family_name}
                  )
              )\
          .WhereElementIsNotElementType()\
          .ToElements()
    return famsyms


def get_elements_by_familytype(family_name, symbol_name, doc=None):
    syms = \
        DB.FilteredElementCollector(doc or HOST_APP.doc)\
          .WherePasses(
              get_biparam_stringequals_filter(
                  {DB.BuiltInParameter.SYMBOL_FAMILY_NAME_PARAM: family_name,
                   DB.BuiltInParameter.SYMBOL_NAME_PARAM: symbol_name
                   }
                  )
              )\
          .WhereElementIsNotElementType()\
          .ToElements()
    return syms


def find_workset(workset_name_or_list, doc=None, partial=True):
    workset_clctr = \
        DB.FilteredWorksetCollector(doc or HOST_APP.doc).ToWorksets()
    if isinstance(workset_name_or_list, list):
        for workset in workset_clctr:
            for workset_name in workset_name_or_list:
                if workset_name in workset.Name:
                    return workset

    elif isinstance(workset_name_or_list, str):
        workset_name = workset_name_or_list

        if partial:
            for workset in workset_clctr:
                if workset_name in workset.Name:
                    return workset
        else:
            for workset in workset_clctr:
                if workset_name == workset.Name:
                    return workset


def model_has_family(family_name, doc=None):
    collector = get_family(family_name, doc=doc)
    return hasattr(collector, 'Count') and collector.Count > 0


def model_has_workset(workset_name, partial=False, doc=None):
    return find_workset(workset_name, partial=partial, doc=doc)


def get_sharedparam_definition_file():
    if HOST_APP.app.SharedParametersFilename:
        sparamf = HOST_APP.app.OpenSharedParameterFile()
        if sparamf:
            return sparamf
        else:
            raise PyRevitException('Failed opening Shared Parameters file.')
    else:
        raise PyRevitException('No Shared Parameters file defined.')


def get_defined_sharedparams():
    # returns DB.ExternalDefinition
    pp_list = []
    try:
        for def_group in get_sharedparam_definition_file().Groups:
            pp_list.extend([x for x in def_group.Definitions])
    except PyRevitException as ex:
        mlogger.debug('Error getting shared parameters. | %s', ex)
    return pp_list


def get_project_parameters(doc=None):
    doc = doc or HOST_APP.doc
    # collect shared parameter names
    shared_params = {x.Name: x for x in get_defined_sharedparams()}

    pp_list = []
    if doc and not doc.IsFamilyDocument:
        param_bindings = doc.ParameterBindings
        pb_iterator = param_bindings.ForwardIterator()
        pb_iterator.Reset()

        while pb_iterator.MoveNext():
            msp = db.ProjectParameter(
                pb_iterator.Key,
                param_bindings[pb_iterator.Key],
                param_ext_def=shared_params.get(pb_iterator.Key.Name, None))
            pp_list.append(msp)

    return pp_list


def get_project_parameter_id(param_name):
    for project_param in get_project_parameters():
        if project_param.name == param_name:
            return project_param.param_id
    raise PyRevitException('Parameter not found: {}'.format(param_name))


def get_project_parameter(param_id_or_name, doc=None):
    pp_list = get_project_parameters(doc or HOST_APP.doc)
    for msp in pp_list:
        if msp == param_id_or_name:
            return msp


def model_has_parameter(param_id_or_name, doc=None):
    return get_project_parameter(param_id_or_name, doc=doc)


def get_project_info(doc=None):
    return db.ProjectInfo(doc or HOST_APP.doc)


def get_revisions(doc=None):
    return list(DB.FilteredElementCollector(doc or HOST_APP.doc)
                .OfCategory(DB.BuiltInCategory.OST_Revisions)
                .WhereElementIsNotElementType())


def get_sheet_revisions(sheet, doc=None):
    doc = doc or HOST_APP.doc
    return [doc.GetElement(x) for x in sheet.GetAdditionalRevisionIds()]


def get_sheets(include_placeholders=True, include_noappear=True, doc=None):
    sheets = list(DB.FilteredElementCollector(doc or HOST_APP.doc)
                  .OfCategory(DB.BuiltInCategory.OST_Sheets)
                  .WhereElementIsNotElementType())
    if not include_noappear:
        sheets = [x for x in sheets
                  if x.Parameter[DB.BuiltInParameter.SHEET_SCHEDULED]
                  .AsInteger() > 0]
    if not include_placeholders:
        return [x for x in sheets if not x.IsPlaceholder]

    return sheets


def get_links(linktype=None, doc=None):
    doc = doc or HOST_APP.doc

    location = doc.PathName
    if not location:
        raise PyRevitException('PathName is empty. Model is not saved.')

    links = []
    model_path = \
        DB.ModelPathUtils.ConvertUserVisiblePathToModelPath(location)
    if not model_path:
        raise PyRevitException('Model is not saved. Can not read links.')
    try:
        trans_data = DB.TransmissionData.ReadTransmissionData(model_path)
        external_refs = trans_data.GetAllExternalFileReferenceIds()
        for ref_id in external_refs:
            ext_ref = trans_data.GetLastSavedReferenceData(ref_id)
            link = doc.GetElement(ref_id)
            if linktype:
                if ext_ref.ExternalFileReferenceType == linktype:
                    links.append(db.ExternalRef(link, ext_ref))
            else:
                links.append(db.ExternalRef(link, ext_ref))
        return links
    except Exception as data_err:
        raise PyRevitException('Error reading links from model path: {} | {}'
                               .format(model_path, data_err))


def get_linked_models(doc=None, loaded_only=False):
    doc = doc or HOST_APP.doc
    linkedmodels = get_links(linktype=DB.ExternalFileReferenceType.RevitLink,
                             doc=doc)
    if loaded_only:
        return [x for x in linkedmodels
                if DB.RevitLinkType.IsLoaded(doc, x.id)]

    return linkedmodels


def get_linked_model_doc(linked_model):
    lmodel = None
    if isinstance(linked_model, DB.RevitLinkType):
        lmodel = db.ExternalRef(linked_model) #pylint: disable=E1120
    elif isinstance(linked_model, db.ExternalRef):
        lmodel = linked_model

    if lmodel:
        for open_doc in HOST_APP.docs:
            if open_doc.Title == lmodel.name:
                return open_doc


def find_first_legend(doc=None):
    doc = doc or HOST_APP.doc
    for view in DB.FilteredElementCollector(doc).OfClass(DB.View):
        if view.ViewType == DB.ViewType.Legend:
            return view
    return None


def compare_revisions(src_rev, dest_rev, case_sensitive=False):
    return all(db.BaseWrapper.compare_attrs(src_rev, dest_rev,
                                            ['RevisionDate',
                                             'Description',
                                             'IssuedBy',
                                             'IssuedTo'],
                                            case_sensitive=case_sensitive))


def get_all_views(doc=None, view_types=None, include_nongraphical=False):
    doc = doc or HOST_APP.doc
    all_views = DB.FilteredElementCollector(doc) \
                  .OfClass(DB.View) \
                  .WhereElementIsNotElementType() \
                  .ToElements()

    if view_types:
        all_views = [x for x in all_views if x.ViewType in view_types]

    if not include_nongraphical:
        return [x for x in all_views
                if x.ViewType in GRAPHICAL_VIEWTYPES
                and not x.IsTemplate
                and not x.ViewSpecific]

    return all_views


def get_all_view_templates(doc=None, view_types=None):
    return [x for x in get_all_views(doc=doc,
                                     view_types=view_types,
                                     include_nongraphical=True)
            if x.IsTemplate]


def get_sheet_by_number(sheet_num, doc=None):
    doc = doc or HOST_APP.doc
    return next((x for x in get_sheets(doc=doc)
                 if x.SheetNumber == sheet_num), None)


def get_viewport_by_number(sheet_num, detail_num, doc=None):
    doc = doc or HOST_APP.doc
    sheet = get_sheet_by_number(sheet_num, doc=doc)
    if sheet:
        vps = [doc.GetElement(x) for x in sheet.GetAllViewports()]
        for vp in vps:
            det_num = vp.Parameter[
                DB.BuiltInParameter.VIEWPORT_DETAIL_NUMBER
                ].AsString()
            if det_num == detail_num:
                return vp


def get_view_by_sheetref(sheet_num, detail_num, doc=None):
    doc = doc or HOST_APP.doc
    vport = get_viewport_by_number(sheet_num, detail_num, doc=doc)
    if vport:
        return vport.ViewId


def get_all_schedules(doc=None):
    doc = doc or HOST_APP.doc
    all_scheds = DB.FilteredElementCollector(doc) \
                   .OfClass(DB.ViewSchedule) \
                   .WhereElementIsNotElementType() \
                   .ToElements()
    return all_scheds


def get_view_by_name(view_name, doc=None):
    doc = doc or HOST_APP.doc
    for view in get_all_views(doc=doc):
        if get_name(view) == view_name:
            return view


def get_all_referencing_elements(doc=None):
    doc = doc or HOST_APP.doc
    all_referencing_elements = []
    for el in DB.FilteredElementCollector(doc)\
                .WhereElementIsNotElementType()\
                .ToElements():
        if el.Category \
                and isinstance(el, DB.Element) \
                and get_builtincategory(el.Category) in BUILTINCATEGORIES_VIEW:
            all_referencing_elements.append(el.Id)
    return all_referencing_elements


def get_all_referencing_elements_in_view(view):
    all_referencing_elements_in_view = []
    for el in DB.FilteredElementCollector(view.Document, view.Id)\
                .WhereElementIsNotElementType()\
                .ToElements():
        if el.Category \
                and isinstance(el, DB.Element) \
                and get_builtincategory(el.Category) in BUILTINCATEGORIES_VIEW:
            all_referencing_elements_in_view.append(el.Id)
    return all_referencing_elements_in_view


def get_schedules_on_sheet(viewsheet, doc=None):
    doc = doc or HOST_APP.doc
    all_sheeted_scheds = DB.FilteredElementCollector(doc)\
                           .OfClass(DB.ScheduleSheetInstance)\
                           .ToElements()
    return [x for x in all_sheeted_scheds
            if x.OwnerViewId == viewsheet.Id
            and not doc.GetElement(x.ScheduleId).IsTitleblockRevisionSchedule]


def is_sheet_empty(viewsheet):
    sheet_views = viewsheet.GetAllViewports()
    sheet_scheds = get_schedules_on_sheet(viewsheet, doc=viewsheet.Document)
    if sheet_views or sheet_scheds:
        return False
    return True


def get_doc_categories(doc=None):
    doc = doc or HOST_APP.doc
    all_cats = []
    cats = doc.Settings.Categories
    all_cats.extend(cats)
    for cat in cats:
        all_cats.extend([x for x in cat.SubCategories])
    return all_cats


def get_schedule_categories():
    all_cats = get_doc_categories()
    cats = []
    for cat_id in DB.ViewSchedule.GetValidCategoriesForSchedule():
        for cat in all_cats:
            if cat.Id.IntegerValue == cat_id.IntegerValue:
                cats.append(cat)
    return cats


def get_key_schedule_categories():
    all_cats = get_doc_categories()
    cats = []
    for cat_id in DB.ViewSchedule.GetValidCategoriesForKeySchedule():
        for cat in all_cats:
            if cat.Id.IntegerValue == cat_id.IntegerValue:
                cats.append(cat)
    return cats


def get_takeoff_categories():
    all_cats = get_doc_categories()
    cats = []
    for cat_id in DB.ViewSchedule.GetValidCategoriesForMaterialTakeoff():
        for cat in all_cats:
            if cat.Id.IntegerValue == cat_id.IntegerValue:
                cats.append(cat)
    return cats


def get_category(cat_name_or_builtin, doc=None):
    doc = doc or HOST_APP.doc
    all_cats = get_doc_categories()
    if isinstance(cat_name_or_builtin, str):
        for cat in all_cats:
            if cat.Name == cat_name_or_builtin:
                return cat
    elif isinstance(cat_name_or_builtin, DB.BuiltInCategory):
        for cat in all_cats:
            if cat.Id.IntegerValue == int(cat_name_or_builtin):
                return cat
    elif isinstance(cat_name_or_builtin, DB.Category):
        return cat_name_or_builtin


def get_builtincategory(cat_name_or_id, doc=None):
    doc = doc or HOST_APP.doc
    cat_id = None
    if isinstance(cat_name_or_id, str):
        cat = get_category(cat_name_or_id)
        if cat:
            cat_id = cat.Id.IntegerValue
    elif isinstance(cat_name_or_id, DB.ElementId):
        cat_id = cat_name_or_id.IntegerValue
    if cat_id:
        for bicat in DB.BuiltInCategory.GetValues(DB.BuiltInCategory):
            if int(bicat) == cat_id:
                return bicat


def get_builtinparameter(element, param_name, doc=None):
    doc = doc or HOST_APP.doc
    eparam = element.LookupParameter(param_name)
    if eparam:
        for biparam in DB.BuiltInParameter.GetValues(DB.BuiltInParameter):
            if int(biparam) == eparam.Definition.Id.IntegerValue:
                return biparam


def get_view_cutplane_offset(view):
    viewrange = view.GetViewRange()
    return viewrange.GetOffset(DB.PlanViewPlane.CutPlane)


def get_project_location_transform(doc=None):
    doc = doc or HOST_APP.doc
    return doc.ActiveProjectLocation.GetTransform()


def get_all_linkedmodels(doc=None):
    doc = doc or HOST_APP.doc
    return DB.FilteredElementCollector(doc)\
             .OfClass(DB.RevitLinkType)\
             .ToElements()


def get_all_linkeddocs(doc=None):
    doc = doc or HOST_APP.doc
    linkinstances = DB.FilteredElementCollector(doc)\
                      .OfClass(DB.RevitLinkInstance)\
                      .ToElements()
    return {x.GetLinkDocument() for x in linkinstances}


def get_all_grids(group_by_direction=False,
                  include_linked_models=False, doc=None):
    doc = doc or HOST_APP.doc
    target_docs = [doc]
    if include_linked_models:
        target_docs.extend(get_all_linkeddocs())

    all_grids = []
    for tdoc in target_docs:
        if tdoc is not None:
            all_grids.extend(list(
                DB.FilteredElementCollector(tdoc)
                .OfCategory(DB.BuiltInCategory.OST_Grids)
                .WhereElementIsNotElementType()
                .ToElements()
                ))

    if group_by_direction:
        direcs = {db.XYZPoint(x.Curve.Direction) for x in all_grids}
        grouped_grids = {}
        for direc in direcs:
            grouped_grids[direc] = [x for x in all_grids
                                    if direc == db.XYZPoint(x.Curve.Direction)]
        return grouped_grids
    return all_grids


def get_gridpoints(grids=None, include_linked_models=False, doc=None):
    doc = doc or HOST_APP.doc
    source_grids = grids or get_all_grids(
        doc=doc,
        include_linked_models=include_linked_models
        )
    gints = {}
    for grid1 in source_grids:
        for grid2 in source_grids:
            results = framework.clr.Reference[DB.IntersectionResultArray]()
            intres = grid1.Curve.Intersect(grid2.Curve, results)
            if intres == DB.SetComparisonResult.Overlap:
                gints[db.XYZPoint(results.get_Item(0).XYZPoint)] = \
                    [grid1, grid2]
    return [GridPoint(point=k, grids=v) for k, v in gints.items()]


def get_closest_gridpoint(element, gridpoints):
    dist = (gridpoints[0].point.unwrap().DistanceTo(element.Location.Point),
            gridpoints[0])
    for grid_point in gridpoints:
        gp_dist = grid_point.point.unwrap().DistanceTo(element.Location.Point)
        if gp_dist < dist[0]:
            dist = (gp_dist, grid_point)
    return dist[1]


def get_category_set(category_list, doc=None):
    doc = doc or HOST_APP.doc
    cat_set = HOST_APP.app.Create.NewCategorySet()
    for builtin_cat in category_list:
        cat = doc.Settings.Categories.get_Item(builtin_cat)
        cat_set.Insert(cat)
    return cat_set


def get_all_category_set(bindable=True, doc=None):
    doc = doc or HOST_APP.doc
    cat_set = HOST_APP.app.Create.NewCategorySet()
    for cat in doc.Settings.Categories:
        if bindable:
            if cat.AllowsBoundParameters:
                cat_set.Insert(cat)
        else:
            cat_set.Insert(cat)
    return cat_set


def get_rule_filters(doc=None):
    doc = doc or HOST_APP.doc
    rfcl = DB.FilteredElementCollector(doc)\
             .OfClass(DB.ParameterFilterElement)\
             .WhereElementIsNotElementType()\
             .ToElements()
    return list(rfcl)


def get_connected_circuits(element, spare=False, space=False):
    circuit_types = [DB.Electrical.CircuitType.Circuit]
    if spare:
        circuit_types.append(DB.Electrical.CircuitType.Spare)
    if space:
        circuit_types.append(DB.Electrical.CircuitType.Space)

    if element.MEPModel and element.MEPModel.ElectricalSystems:
        return [x for x in element.MEPModel.ElectricalSystems
                if x.CircuitType in circuit_types]


def get_element_categories(elements):
    catsdict = {x.Category.Name: x.Category for x in elements}
    uniquenames = set(catsdict.keys())
    return [catsdict[x] for x in uniquenames]


def get_category_schedules(category_or_catname, doc=None):
    doc = doc or HOST_APP.doc
    cat = get_category(category_or_catname)
    scheds = get_all_schedules(doc=doc)
    return [x for x in scheds if x.Definition.CategoryId == cat.Id]


def get_schedule_field(schedule, field_name):
    for field_idx in schedule.Definition.GetFieldOrder():
        field = schedule.Definition.GetField(field_idx)
        if field.GetName() == field_name:
            return field


def get_schedule_filters(schedule, field_name, return_index=False):
    matching_filters = []
    field = get_schedule_field(schedule, field_name)
    if field:
        for idx, sfilter in enumerate(schedule.Definition.GetFilters()):
            if sfilter.FieldId == field.FieldId:
                if return_index:
                    matching_filters.append(idx)
                else:
                    matching_filters.append(sfilter)
    return matching_filters


def get_sheet_tblocks(src_sheet):
    sheet_tblocks = DB.FilteredElementCollector(src_sheet.Document,
                                                src_sheet.Id)\
                      .OfCategory(DB.BuiltInCategory.OST_TitleBlocks)\
                      .WhereElementIsNotElementType()\
                      .ToElements()
    return list(sheet_tblocks)


def get_sheet_sets(doc=None):
    doc = doc or HOST_APP.doc
    viewsheetsets = DB.FilteredElementCollector(doc)\
                      .OfClass(DB.ViewSheetSet)\
                      .WhereElementIsNotElementType()\
                      .ToElements()
    return list(viewsheetsets)


def get_rev_number(revision):
    revnum = revision.SequenceNumber
    if hasattr(revision, 'RevisionNumber'):
        revnum = revision.RevisionNumber
    return revnum


def get_pointclouds(doc=None):
    doc = doc or HOST_APP.doc
    return get_elements_by_category([DB.BuiltInCategory.OST_PointClouds],
                                    doc=doc)


def get_mep_connections(element):
    connmgr = None
    if isinstance(element, DB.FamilyInstance):
        connmgr = element.MEPModel.ConnectorManager
    elif isinstance(element, DB.Plumbing.Pipe):
        connmgr = element.ConnectorManager

    if connmgr:
        connelements = [y.Owner
                        for x in connmgr.Connectors
                        for y in x.AllRefs
                        if x.IsConnected
                        and y.Owner.Id != element.Id
                        and y.ConnectorType != DB.ConnectorType.Logical]
        return connelements


def get_fillpattern_element(fillpattern_name, fillpattern_target, doc=None):
    doc = doc or HOST_APP.doc
    existing_fp_elements = \
        DB.FilteredElementCollector(doc) \
          .OfClass(framework.get_type(DB.FillPatternElement))

    for existing_fp_element in existing_fp_elements:
        fillpattern = existing_fp_element.GetFillPattern()
        if fillpattern_name == fillpattern.Name \
                and fillpattern_target == fillpattern.Target:
            return existing_fp_element


def get_all_fillpattern_elements(fillpattern_target, doc=None):
    doc = doc or HOST_APP.doc
    existing_fp_elements = \
        DB.FilteredElementCollector(doc) \
          .OfClass(framework.get_type(DB.FillPatternElement))

    return [x for x in existing_fp_elements
            if x.GetFillPattern().Target == fillpattern_target]


def get_subcategories(doc=None, purgable=False, filterfunc=None):
    doc = doc or HOST_APP.doc
    # collect custom categories
    subcategories = []
    for cat in doc.Settings.Categories:
        for subcat in cat.SubCategories:
            if purgable:
                if subcat.Id.IntegerValue > 1:
                    subcategories.append(subcat)
            else:
                subcategories.append(subcat)
    if filterfunc:
        subcategories = filter(filterfunc, subcategories)

    return subcategories


def get_subcategory(category_name, subcategory_name, doc=None):
    doc = doc or HOST_APP.doc
    for cat in doc.Settings.Categories:
        if cat.Name == category_name:
            for subcat in cat.SubCategories:
                if subcat.Name == subcategory_name:
                    return subcat


def get_keynote_file(doc=None):
    doc = doc or HOST_APP.doc
    knote_table = DB.KeynoteTable.GetKeynoteTable(doc)
    knote_table_ref = knote_table.GetExternalFileReference()
    return DB.ModelPathUtils.ConvertModelPathToUserVisiblePath(
        knote_table_ref.GetAbsolutePath()
        )


def get_used_keynotes(doc=None):
    doc = doc or HOST_APP.doc
    return DB.FilteredElementCollector(doc)\
             .OfCategory(DB.BuiltInCategory.OST_KeynoteTags)\
             .WhereElementIsNotElementType()\
             .ToElements()


def get_visible_keynotes(view=None):
    doc = view.Document
    return DB.FilteredElementCollector(doc, view.Id)\
             .OfCategory(DB.BuiltInCategory.OST_KeynoteTags)\
             .WhereElementIsNotElementType()\
             .ToElements()


def get_available_keynotes(doc=None):
    doc = doc or HOST_APP.doc
    knote_table = DB.KeynoteTable.GetKeynoteTable(doc)
    return knote_table.GetKeyBasedTreeEntries()


def get_available_keynotes_tree(doc=None):
    doc = doc or HOST_APP.doc
    knotes = get_available_keynotes(doc=doc)
    # TODO: implement knotes tree
    raise NotImplementedError()


def is_placed(spatial_element):
    return isinstance(spatial_element,
                      (DB.Architecture.Room, DB.Area, DB.Mechanical.Space)) \
            and spatial_element.Area > 0


def get_central_path(doc=None):
    doc = doc or HOST_APP.doc
    if doc.IsWorkshared:
        model_path = doc.GetWorksharingCentralModelPath()
        return DB.ModelPathUtils.ConvertModelPathToUserVisiblePath(model_path)


def is_metric(doc=None):
    doc = doc or HOST_APP.doc
    return doc.DisplayUnitSystem == DB.DisplayUnit.METRIC


def is_imperial(doc=None):
    doc = doc or HOST_APP.doc
    return doc.DisplayUnitSystem == DB.DisplayUnit.IMPERIAL


def get_view_sheetrefinfo(view):
    # grab sheet number and name
    # this looks at 'Sheet Number' and 'Sheet Name' parameters of a view
    # if these parameters have value, it means view is placed on a sheet
    sheet_num = \
        view.Parameter[DB.BuiltInParameter.VIEWPORT_SHEET_NUMBER].AsString()
    sheet_name = \
        view.Parameter[DB.BuiltInParameter.VIEWPORT_SHEET_NAME].AsString()
    # grab detail number as well
    detail_num = \
        view.Parameter[DB.BuiltInParameter.VIEWPORT_DETAIL_NUMBER].AsString()

    if sheet_num:
        return SheetRefInfo(
            sheet_num=sheet_num,
            sheet_name=sheet_name,
            detail_num=detail_num,
            ref_viewid=None
            )

    # if not, check 'Referencing Sheet' and 'Referencing Detail' parameters
    # these show that the view is referened by another on that sheet
    ref_sheet_num = \
        view.Parameter[DB.BuiltInParameter.VIEW_REFERENCING_SHEET].AsString()
    ref_sheet = get_sheet_by_number(ref_sheet_num)
    ref_sheet_name = get_name(ref_sheet) if ref_sheet else ''
    # grab referring detail number as well
    ref_detail_num = \
        view.Parameter[DB.BuiltInParameter.VIEW_REFERENCING_DETAIL].AsString()

    if ref_sheet_num:
        return SheetRefInfo(
            sheet_num=ref_sheet_num,
            sheet_name=ref_sheet_name,
            detail_num=ref_detail_num,
            ref_viewid=get_view_by_sheetref(ref_sheet_num, ref_detail_num)
            )


def get_all_sheeted_views(doc=None, sheets=None):
    doc = doc or HOST_APP.doc
    sheets = sheets or get_sheets(doc=doc)
    all_sheeted_view_ids = set()
    for sht in sheets:
        vp_ids = [doc.GetElement(x).ViewId for x in sht.GetAllViewports()]
        all_sheeted_view_ids.update(vp_ids)
    return all_sheeted_view_ids


def is_view_sheeted(view):
    return view.Id in get_all_sheeted_views(doc=view.Document)


def can_refer_other_views(source_view):
    return isinstance(source_view,
                      (DB.ViewDrafting, DB.ViewPlan, DB.ViewSection))


def is_referring_to(source_view, target_view):
    # if view can be referring
    doc = source_view.Document
    target_viewname = get_name(target_view)

    if can_refer_other_views(source_view):
        for ref_elid in get_all_referencing_elements_in_view(source_view):
            viewref_el = doc.GetElement(ref_elid)
            targetview_param = \
                    viewref_el.Parameter[
                        DB.BuiltInParameter.REFERENCE_VIEWER_TARGET_VIEW
                        ]
            if targetview_param:
                tvp_view = doc.GetElement(targetview_param.AsElementId())
                if tvp_view and get_name(tvp_view) == target_viewname:
                    return True
            else:
                viewref_name = get_name(viewref_el)
                if viewref_name == target_viewname:
                    return True


def yield_referring_views(target_view, all_views=None):
    all_views = all_views or get_all_views(doc=target_view.Document)
    for view in all_views:
        if is_referring_to(view, target_view):
            yield view.Id


def yield_referenced_views(doc=None, all_views=None):
    doc = doc or HOST_APP.doc
    all_views = all_views or get_all_views(doc=doc)
    for view in all_views:
        # if it has any referring views, yield
        if next(yield_referring_views(view), None):
            yield view.Id


def yield_unreferenced_views(doc=None, all_views=None):
    doc = doc or HOST_APP.doc
    all_views = all_views or get_all_views(doc=doc)
    for view in all_views:
        # if it has NO referring views, yield
        if len(list(yield_referring_views(view))) == 0:
            yield view.Id


def get_line_categories(doc=None):
    doc = doc or HOST_APP.doc
    lines_cat = doc.Settings.Categories.get_Item(DB.BuiltInCategory.OST_Lines)
    return lines_cat.SubCategories


def get_line_styles(doc=None):
    return [x.GetGraphicsStyle(DB.GraphicsStyleType.Projection)
            for x in get_line_categories(doc=doc)]


def get_history(target_element):
    doc = target_element.Document
    if doc.IsWorkshared:
        wti = DB.WorksharingUtils.GetWorksharingTooltipInfo(doc,
                                                            target_element.Id)
        return ElementHistory(creator=wti.Creator,
                              owner=wti.Owner,
                              last_changed_by=wti.LastChangedBy)


def is_detail_curve(element):
    return isinstance(element, DETAIL_CURVES)


def is_model_curve(element):
    return isinstance(element, MODEL_CURVES)


def is_sketch_curve(element):
    if element.Category:
        cid = element.Category.Id
        return cid == DB.ElementId(DB.BuiltInCategory.OST_SketchLines)


def get_all_schemas():
    return DB.ExtensibleStorage.Schema.ListSchemas()


def get_schema_field_values(element, schema):
    field_values = {}
    entity = element.GetEntity(schema)
    if entity:
        for field in schema.ListFields():
            field_type = field.ValueType
            if field.ContainerType == DB.ExtensibleStorage.ContainerType.Array:
                field_type = framework.IList[field.ValueType]
            elif field.ContainerType == DB.ExtensibleStorage.ContainerType.Map:
                field_type = \
                    framework.IDictionary[field.KeyType, field.ValueType]
            try:
                value = entity.Get[field_type](
                    field.FieldName,
                    DB.DisplayUnitType.DUT_UNDEFINED
                    )
            except:
                value = None

            field_values[field.FieldName] = value
    return field_values


def get_family_type(type_name, family_doc):
    if family_doc.IsFamilyDocument:
        for ftype in family_doc.FamilyManager.Types:
            if ftype.Name == type_name:
                return ftype
    else:
        raise PyRevitException('Document is not a family')


def get_family_parameter(param_name, family_doc):
    if family_doc.IsFamilyDocument:
        for fparam in family_doc.FamilyManager.GetParameters():
            if fparam.Definition.Name == param_name:
                return fparam
    else:
        raise PyRevitException('Document is not a family')
