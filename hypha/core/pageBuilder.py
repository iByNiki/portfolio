import hypha.core.builder as builder
import hypha.core.parser as parser
from hypha.core.structures import *
from bs4 import BeautifulSoup
import re
import json
import cssutils
import logging

cssutils.log.setLevel(logging.FATAL)

class PageBuilder(object):
    def __init__(self):
        self.pageDir = "pages"
        self.layoutDir = "layouts"
        self.componentDir = "components"

        self.components = {}
        self.layouts = {}
        self.pages = {}

        self.scopedClasses = []

    def parseConfig(self, configText):
        return json.loads(configText)
    
    def parseTemplate(self, template, scopePrefix, parentComponent=None):

        foundComponents = []

        # CSS Scoping
        elements = template.find_all(class_=True)
        for element in elements:
            if (not element.has_attr("class")): continue
            classListRaw = element["class"]
            classList = []
            initialName = " ".join(element["class"])

            toScope = 0

            for className in classListRaw:

                if (className in self.scopedClasses):
                    newClassName = scopePrefix + "-" + className
                    toScope += 1
                else: newClassName = className

                classList.append(newClassName)
            
            newClassName = " ".join(classList)

            replaceElem = template.find(attrs={"class", " ".join(element["class"])})
            while (replaceElem != None and toScope > 0):
                template.find(attrs={"class", initialName})["class"] = newClassName
                
                replaceElem = template.find(attrs={"class", initialName})
            
            element.attrs["h-id"] = scopePrefix # set element id for reference in js

        # Component replacement
        foundComponents = []

        innerHTML = builder.getInnerHTML(template)
        matches = re.findall("<[a-zA-z]*.*/>", innerHTML)

        componentList = [builder.dirName(p).lower() for p in builder.getComponentPaths()]

        for elem in template.findAll():
            componentName = elem.name.replace(".", "/")

            processElem = False
            if (componentName in self.components):
                processElem = True

                foundComponents.append(componentName)
                component = self.components[componentName]

                foundComponents += component.requiredComponents

            elif (componentName in componentList):
                processElem = True

                foundComponents.append(componentName)

                component = self.buildSingleComponent(builder.getSoup("components/" + componentName.replace(".", "/") + ".php"), componentName)
                self.components[componentName] = component

                foundComponents += component.requiredComponents

            if (processElem):
                newContent = component.content

                if (elem.attrs != None):
                    varMatches = re.findall("\|\|.*?\|\|", newContent)
                    for varMatch in varMatches:
                        matchName = varMatch[2:len(varMatch) - 2]
                        matchReplace = ""
                        if (matchName in elem.attrs):
                            matchReplace = elem.attrs[matchName]

                        newContent = newContent.replace(varMatch, matchReplace)

                elemInner = builder.getInnerHTML(elem)
                processedSlot, temp = self.parseTemplate(BeautifulSoup(elemInner, "html.parser"), scopePrefix)
                newContent = newContent.replace("<slot></slot>", processedSlot)

                innerHTML = innerHTML.replace(str(elem), newContent)

        # Route URL parameters
        argMatches = re.findall("\[\[.*?\]\]", innerHTML)
        for argMatch in argMatches:
            innerHTML = innerHTML.replace(
                argMatch,
                '<?php echo $request["params"]["' + argMatch[2:-2] + '"] ?>')

        if (len(argMatches) > 0):
            jsArgArray = "[" + ",".join(['["' + argMatch[2:-2] +'", "<?php echo $request["params"]["' + argMatch[2:-2] + '"] ?>"]' for match in argMatches]) + "]"
            innerHTML += '<script>hypha.addRouteParams(' + jsArgArray + ')</script>'

        innerHTML = innerHTML.replace("<?php", "<!--<?php").replace("?>", "?>-->")
        innerHTML = str(BeautifulSoup(innerHTML, "html.parser"))
        innerHTML = innerHTML.replace("<!--<?php", "<?php").replace("?>-->", "?>")

        foundComponents = list(set(foundComponents))

        return innerHTML, foundComponents

    def buildSingleComponent(self, soup, name):
        templateElem = soup.find("template")
        styleElem = soup.find("style")
        configElem = soup.find("config")
        scriptElems = soup.find_all("script")

        component = Component(name)

        scopePrefix = "c" + str(len(self.components))

        for scriptElem in scriptElems:
            component.scripts.append(parser.parseJS(scriptElem))

        if (styleElem != None):
            component.css = parser.parseCss(styleElem, self.scopedClasses, scopePrefix)

        if (templateElem != None):
            component.content, component.requiredComponents = self.parseTemplate(templateElem, scopePrefix, parentComponent=name)

        return component


    def buildComponents(self):
        for componentPath in builder.getComponentPaths():
            soup = builder.getSoup(componentPath)
            name = builder.dirName(componentPath).lower().replace("/", ".").replace("\\", ".")

            if (name not in self.components):
                self.components[name] = self.buildSingleComponent(soup, name)

    def buildDefaultComponents(self):
        for componentPath in builder.getDefaultComponentPaths():
            soup = builder.getSoup(componentPath)
            name = builder.dirName(builder.dirName(componentPath)).lower()

            if (name not in self.components):
                self.components[name] = self.buildSingleComponent(soup, name)
            
    def buildSingleLayout(self, soup, name):
        templateElem = soup.find("template")
        styleElem = soup.find("style")
        configElem = soup.find("config")
        scriptElems = soup.find_all("script")
        headElem = soup.find("head")

        layout = Layout(name)

        scopePrefix = "l" + str(len(self.layouts))

        if (headElem != None):
            layout.head, layout.requiredComponents = self.parseTemplate(headElem, scopePrefix)

        if (configElem != None):
            parsedConfig = self.parseConfig(builder.getInnerHTML(configElem))
            layout.config = parsedConfig

        for scriptElem in scriptElems:
            layout.scripts.append(parser.parseJS(scriptElem))

        if (styleElem != None):
            layout.css = parser.parseCss(styleElem, self.scopedClasses, scopePrefix)

        if (templateElem != None):
            layout.content, requiredComponents = self.parseTemplate(templateElem, scopePrefix)
            layout.requiredComponents += requiredComponents
        
        return layout

    def buildLayouts(self):
        for layoutPath in builder.getLayoutPaths():
            soup = builder.getSoup(layoutPath)
            name = builder.dirName(layoutPath)

            if (name not in self.layouts):
                self.layouts[name] = self.buildSingleLayout(soup, name)
    
    def buildSinglePage(self, soup, name):
        templateElem = soup.find("template")
        styleElem = soup.find("style")
        configElem = soup.find("config")
        scriptElems = soup.find_all("script")
        headElem = soup.find("head")

        page = Page(name)

        scopePrefix = "p" + str(len(self.pages))

        if (headElem != None):
            page.head, page.requiredComponents = self.parseTemplate(headElem, scopePrefix)

        for scriptElem in scriptElems:
            page.scripts.append(parser.parseJS(scriptElem))

        if (styleElem != None):
            page.css = parser.parseCss(styleElem, self.scopedClasses, scopePrefix)

        if (templateElem != None):
            page.content, requiredComponents = self.parseTemplate(templateElem, scopePrefix)
            page.requiredComponents += requiredComponents
        
        if (configElem != None):
            parsedConfig = self.parseConfig(builder.getInnerHTML(configElem))
            page.config = parsedConfig

            if ("layout" in page.config):
                layoutName = page.config["layout"]
                if (layoutName.lower() != "none"):
                    if (layoutName not in self.layouts):
                        raise Exception("Layout " + str(layoutName) + " not found. Error in page " + str(name))
                    page.layout = layoutName
            else:
                if ("default" in self.layouts):
                    page.layout = "default"
        else:
            if ("default" in self.layouts):
                page.layout = "default"
        
        return page

    def buildPages(self):
        for pagePath in builder.getPagePaths():
            soup = builder.getSoup(pagePath)
            name = builder.dirName(pagePath)

            if (name not in self.pages):
                self.pages[name] = self.buildSinglePage(soup, name)

    def build(self):
        self.buildDefaultComponents()
        self.buildComponents()
        self.buildLayouts()
        self.buildPages()